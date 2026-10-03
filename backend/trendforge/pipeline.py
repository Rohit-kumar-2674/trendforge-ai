import hashlib
import json
import logging
import time
import uuid
from datetime import datetime, timedelta
from typing import Any

from sqlalchemy import delete, func, select
from sqlalchemy.orm import Session

from trendforge.config import Settings
from trendforge.db import Entity, Event, Forecast, Observation, Outcome, ProviderState, Score
from trendforge.forecasting.baseline import MODEL_VERSION, forecast
from trendforge.forecasting.registry import ensure_baseline
from trendforge.providers import providers
from trendforge.providers.base import ProviderBatch, ProviderError, RateLimited, TrendProvider
from trendforge.schemas import utcnow
from trendforge.stocks import technicals
from trendforge.trends.analogues import outcome_class
from trendforge.trends.quality import freshness
from trendforge.trends.relationships import seasonality
from trendforge.trends.scoring import ENGINE_VERSION, analyze, load_weights

logger = logging.getLogger("trendforge.pipeline")


def digest(value: Any) -> str:
    return hashlib.sha256(
        json.dumps(
            value, sort_keys=True, separators=(",", ":"), default=str, allow_nan=False
        ).encode()
    ).hexdigest()


def ingest(session: Session, batch: ProviderBatch) -> dict[str, int]:
    count, duplicates = 0, 0
    for incoming in batch.entities:
        existing = session.get(Entity, incoming.id)
        if existing is None:
            session.add(Entity(**incoming.model_dump(mode="json")))
        else:
            if (
                existing.synthetic != incoming.synthetic
                or existing.primary_metric != incoming.primary_metric
            ):
                raise ProviderError("Incompatible entity provenance or primary metric")
            existing.name = incoming.name
            existing.keywords = incoming.keywords
    session.flush()
    ids = {o.entity_id for o in batch.observations}
    known: set[tuple[str, str, str, datetime]] = (
        set(
            (row[0], row[1], row[2], row[3])
            for row in session.execute(
                select(
                    Observation.entity_id,
                    Observation.provider,
                    Observation.metric,
                    Observation.source_timestamp,
                ).where(Observation.entity_id.in_(ids))
            ).all()
        )
        if ids
        else set()
    )
    for item in batch.observations:
        key = (item.entity_id, item.provider, item.metric, item.source_timestamp)
        if key in known:
            duplicates += 1
            continue
        entity = session.get(Entity, item.entity_id)
        if entity is None or entity.synthetic != item.synthetic:
            raise ProviderError("Observation provenance does not match entity")
        data = item.model_dump()
        detail = data.pop("metadata")
        session.add(Observation(**data, detail=detail))
        known.add(key)
        count += 1
    session.flush()
    return {"inserted": count, "duplicates": duplicates}


def purge_expired(session: Session) -> int:
    cutoff = utcnow() - timedelta(days=29)
    result = session.execute(
        delete(Observation).where(
            Observation.provider == "youtube", Observation.retrieved_at < cutoff
        )
    )
    # Clear cached API metadata when no retained observations exist.
    for entity in session.scalars(select(Entity).where(Entity.id.like("youtube:%"))):
        remaining = session.scalar(
            select(func.count()).select_from(Observation).where(Observation.entity_id == entity.id)
        )
        if not remaining:
            entity.name = "Unavailable YouTube video"
            entity.keywords = []
    return int(result.rowcount or 0)  # type: ignore[attr-defined]


def primary_history(
    session: Session, entity: Entity, cutoff: datetime | None = None
) -> list[Observation]:
    query = select(Observation).where(
        Observation.entity_id == entity.id, Observation.metric == entity.primary_metric
    )
    if cutoff:
        query = query.where(Observation.source_timestamp <= cutoff)
    if entity.id.startswith("youtube:"):
        query = query.where(Observation.retrieved_at >= utcnow() - timedelta(days=29))
    rows = list(session.scalars(query.order_by(Observation.source_timestamp, Observation.id)))
    if not rows:
        return []
    provider = rows[-1].provider
    # One series per provider/metric/unit: never silently splice incompatible feeds.
    rows = [r for r in rows if r.provider == provider and r.unit == rows[-1].unit]
    daily: dict[str, Observation] = {}
    for row in rows:
        daily[row.source_timestamp.date().isoformat()] = row
    return list(daily.values())


def secondary_history(
    session: Session, entity: Entity, rows: list[Observation]
) -> dict[str, list[float]]:
    if not rows:
        return {}
    query = (
        select(Observation)
        .where(
            Observation.entity_id == entity.id,
            Observation.provider == rows[-1].provider,
            Observation.metric != entity.primary_metric,
            Observation.source_timestamp <= rows[-1].source_timestamp,
        )
        .order_by(Observation.source_timestamp)
    )
    metrics: dict[str, dict[str, float]] = {}
    for row in session.scalars(query):
        metrics.setdefault(row.metric, {})[row.source_timestamp.date().isoformat()] = row.value
    days = [r.source_timestamp.date().isoformat() for r in rows]
    return {name: [series[d] for d in days if d in series] for name, series in metrics.items()}


def calculate_entity(session: Session, entity: Entity, settings: Settings) -> bool:
    rows = primary_history(session, entity)
    if not entity.analytics_allowed or len(rows) < 4:
        return False
    y = [r.value for r in rows]
    dates = [r.source_timestamp for r in rows]
    weights = load_weights(settings.domain_weights_path)
    domain_weights = weights.get(entity.domain, weights["default"])
    secondary = secondary_history(session, entity, rows)
    fingerprint = digest(
        {
            "data": [
                (r.metric, r.value, r.source_timestamp.isoformat(), r.provider, r.unit, r.synthetic)
                for r in rows
            ],
            "secondary": secondary,
            "weights": domain_weights,
            "version": ENGINE_VERSION,
        }
    )
    if session.scalar(
        select(Score.id).where(Score.entity_id == entity.id, Score.snapshot_hash == fingerprint)
    ):
        return False
    score = analyze(
        y,
        dates,
        entity.domain,
        entity.cadence,
        secondary=secondary,
        weights=domain_weights,
        sources=1,
    )
    score["primary_provider"] = rows[-1].provider
    score["primary_metric"] = entity.primary_metric
    score["observed_value"] = y[-1]
    score["sample_size"] = len(y)
    score["synthetic"] = entity.synthetic
    score["seasonality"] = seasonality(y)
    score["observation"] = (
        f"{entity.primary_metric} changed {score['growth_7_periods']:+.2f}% over the last 7 observed periods."
    )
    score["analysis"] = (
        f"Momentum index {score['components']['momentum']:.1f}/100; acceleration {score['relative_acceleration']:+.2f} percentage points versus the previous 7-period change."
    )
    score["inference"] = f"Heuristic lifecycle classification: {score['lifecycle_stage']}."
    score["supporting_signals"] = [
        score["observation"],
        f"Positive change in {score['components']['persistence']:.0f}% of the last 14 intervals.",
    ]
    score["contradicting_signals"] = [
        "Only one independent source; cross-platform confirmation is unavailable."
    ]
    if score["relative_acceleration"] < 0:
        score["contradicting_signals"].append(
            "Growth is decelerating relative to the previous 7 periods."
        )
    if entity.synthetic:
        score["contradicting_signals"].append(
            "All values are synthetic and do not describe current real-world trends."
        )
    if rows[-1].provider == "alpha_vantage":
        score["contradicting_signals"].append(
            "Unadjusted prices: splits and dividends can distort indicators and forecasts."
        )
    if entity.primary_metric == "stars":
        score["counter_metrics"] = {
            "net_stars_latest_interval": round(y[-1] - y[-2], 2),
            "stars_per_elapsed_day": round(
                (y[-1] - y[-2]) / max((dates[-1] - dates[-2]).total_seconds() / 86400, 1e-6), 2
            ),
        }
        created = rows[-1].detail.get("created_at")
        if created:
            age_days = max(
                1.0,
                (dates[-1] - datetime.fromisoformat(created.replace("Z", "+00:00"))).total_seconds()
                / 86400,
            )
            score["counter_metrics"]["lifetime_stars_per_day"] = round(y[-1] / age_days, 3)
        score["contradicting_signals"].append(
            "Forecast target is cumulative stars, not future daily adoption. Lifetime average is not recent velocity."
        )
    if entity.domain in ("stocks", "crypto"):
        score["technicals"] = technicals(
            y, secondary.get("volume"), secondary.get("high"), secondary.get("low")
        )
    previous = session.scalar(
        select(Score)
        .where(Score.entity_id == entity.id)
        .order_by(Score.as_of.desc(), Score.id.desc())
    )
    session.add(
        Score(entity_id=entity.id, as_of=dates[-1], snapshot_hash=fingerprint, payload=score)
    )
    events = []
    if score["anomaly_detected"]:
        events.append(("ANOMALY", f"Robust return z-score {score['anomaly_z']}; cause unknown."))
    if score["current_score"] >= 75:
        events.append(("SCORE THRESHOLD", f"Trend score reached {score['current_score']}/100."))
    if previous and previous.payload["lifecycle_stage"] != score["lifecycle_stage"]:
        events.append(
            (
                "LIFECYCLE CHANGE",
                f"{previous.payload['lifecycle_stage']} → {score['lifecycle_stage']}",
            )
        )
    for kind, message in events:
        event_id = digest([entity.id, fingerprint, kind])
        if session.get(Event, event_id) is None:
            session.add(
                Event(
                    id=event_id,
                    entity_id=entity.id,
                    occurred_at=dates[-1],
                    kind=kind,
                    payload={
                        "message": message,
                        "synthetic": entity.synthetic,
                        "evidence_hash": fingerprint,
                        "relationship": "Unknown cause",
                    },
                )
            )
    now = utcnow()
    interval = 72 if entity.cadence == "trading_session" else 24
    current_freshness = freshness(dates[-1], rows[-1].retrieved_at, now, interval)
    # Never issue a 'new' forecast from stale histories or label a backfill prospective.
    if current_freshness["status"] in ("STALE", "UNAVAILABLE"):
        return True
    horizons = [1, 5, 20] if entity.domain in ("stocks", "crypto") else [3, 7, 30]
    for horizon in horizons:
        result = forecast(
            y, horizon, synthetic=entity.synthetic, quality_score=score["quality"]["score"]
        )
        if result.get("probabilities") is None:
            continue
        for analogue in result["analogues"]:
            analogue["start_date"] = dates[analogue["start_index"]].isoformat()
            analogue["end_date"] = dates[analogue["end_index"]].isoformat()
            analogue["outcome_date"] = dates[analogue["outcome_index"]].isoformat()
        result.update(
            {
                "generated_at": now.isoformat(),
                "data_as_of": dates[-1].isoformat(),
                "horizon_unit": "observed trading sessions"
                if entity.cadence == "trading_session"
                else "calendar days",
                "target_metric": entity.primary_metric,
                "target_provider": rows[-1].provider,
                "snapshot_hash": fingerprint,
                "feature_snapshot": score,
                "input_snapshot": {
                    "values": y,
                    "timestamps": [d.isoformat() for d in dates],
                    "retrieved_at": [r.retrieved_at.isoformat() for r in rows],
                    "provider": rows[-1].provider,
                    "unit": entity.unit,
                },
                "configuration": {
                    "weights": domain_weights,
                    "engine_version": ENGINE_VERSION,
                    "analogue_window": 21,
                    "method": "euclidean",
                },
            }
        )
        session.add(
            Forecast(
                id=str(uuid.uuid4()),
                entity_id=entity.id,
                issued_at=now,
                as_of=dates[-1],
                horizon=horizon,
                horizon_unit=entity.cadence,
                target_metric=entity.primary_metric,
                target_provider=rows[-1].provider,
                model_version=MODEL_VERSION,
                snapshot_hash=fingerprint,
                features_hash=digest(score),
                reference_value=y[-1],
                threshold=result["threshold"],
                synthetic=entity.synthetic,
                payload=result,
            )
        )
    session.flush()
    return True


def resolve_outcomes(session: Session) -> int:
    resolved = 0
    unresolved = session.scalars(
        select(Forecast)
        .outerjoin(Outcome, Outcome.forecast_id == Forecast.id)
        .where(Outcome.forecast_id.is_(None))
    )
    for item in list(unresolved):
        entity = session.get(Entity, item.entity_id)
        if entity is None:
            continue
        rows = [
            r
            for r in primary_history(session, entity)
            if r.provider == item.target_provider and r.source_timestamp > item.as_of
        ]
        target: Observation | None = None
        if item.horizon_unit == "trading_session":
            if len(rows) >= item.horizon:
                target = rows[item.horizon - 1]
        else:
            due = item.as_of.date() + timedelta(days=item.horizon)
            target = next((r for r in rows if r.source_timestamp.date() == due), None)
        if target is None or target.source_timestamp <= item.issued_at:
            continue
        change = target.value / max(item.reference_value, 1e-8) - 1
        actual = outcome_class(change, item.threshold)
        session.add(
            Outcome(
                forecast_id=item.id,
                observed_at=target.source_timestamp,
                actual_value=target.value,
                actual_return=change,
                actual_class=actual,
                correct=actual == item.payload["direction"],
            )
        )
        resolved += 1
    session.flush()
    return resolved


async def update(
    session: Session,
    settings: Settings,
    *,
    adapters: list[TrendProvider] | None = None,
    force: bool = False,
) -> dict[str, Any]:
    started = time.monotonic()
    ensure_baseline(session)
    purge_expired(session)
    session.commit()
    results: list[dict[str, Any]] = []
    for provider in adapters if adapters is not None else providers(settings):
        now = utcnow()
        state = session.get(ProviderState, provider.name)
        if state is None:
            state = ProviderState(
                name=provider.name,
                status="NOT CONFIGURED",
                capability=provider.capability,
                message=provider.instructions,
                expected_interval_hours=provider.expected_interval_hours,
                records=0,
                stats={},
            )
            session.add(state)
            session.flush()
        if not provider.configured or (
            settings.demo_mode and provider.name != "demo" and adapters is None
        ):
            state.status = "NOT CONFIGURED"
            state.message = provider.instructions + (
                " Live ingestion is disabled while DEMO_MODE=true." if settings.demo_mode else ""
            )
            session.commit()
            results.append({"provider": provider.name, "status": state.status})
            continue
        if (
            not force
            and state.last_success
            and (now - state.last_success).total_seconds() < provider.expected_interval_hours * 3600
        ):
            results.append(
                {
                    "provider": provider.name,
                    "status": "CACHED",
                    "last_success": state.last_success.isoformat(),
                }
            )
            continue
        try:
            batch = await provider.fetch()
            if not batch.observations and provider.name != "youtube":
                raise ProviderError(
                    "Provider returned no usable observations; cached history retained"
                )
            with session.begin_nested():
                counts = ingest(session, batch)
                if provider.name == "youtube":
                    present = [e.id for e in batch.entities]
                    # Remove API data for videos no longer returned; raw stats never enter forecasts.
                    session.execute(
                        delete(Observation).where(
                            Observation.provider == "youtube", Observation.entity_id.not_in(present)
                        )
                    )
                    purge_expired(session)
            state.status = "DEGRADED" if batch.warnings else "ONLINE"
            state.last_success = now
            state.records += counts["inserted"]
            state.message = (
                "; ".join(sorted(set(batch.warnings)))[:600]
                if batch.warnings
                else provider.instructions
            )
            results.append(
                {
                    "provider": provider.name,
                    "status": state.status,
                    **counts,
                    "warnings": batch.warnings,
                }
            )
        except RateLimited as exc:
            state.status, state.message = "RATE LIMITED", str(exc)
            results.append(
                {"provider": provider.name, "status": state.status, "message": state.message}
            )
        except Exception as exc:
            # Unexpected exceptions are classified without recording URLs, response bodies or credentials.
            state.status = "OFFLINE"
            state.message = (
                str(exc)[:500]
                if isinstance(exc, ProviderError)
                else f"Provider processing failed ({type(exc).__name__}); cached history retained"
            )
            results.append(
                {"provider": provider.name, "status": state.status, "message": state.message}
            )
        state.last_attempt = now
        state.stats = dict(provider.transport.stats)
        session.commit()
    calculated, failures = 0, 0
    for entity in list(
        session.scalars(select(Entity).where(Entity.synthetic == settings.demo_mode))
    ):
        try:
            with session.begin_nested():
                calculated += int(calculate_entity(session, entity, settings))
            session.commit()
        except Exception as exc:
            session.rollback()
            failures += 1
            logger.error(
                json.dumps(
                    {
                        "event": "entity_analysis_failed",
                        "entity": entity.id,
                        "error_type": type(exc).__name__,
                    }
                )
            )
    resolved = resolve_outcomes(session)
    session.commit()
    summary = {
        "providers": results,
        "entities_recalculated": calculated,
        "analysis_failures": failures,
        "outcomes_resolved": resolved,
        "duration_seconds": round(time.monotonic() - started, 2),
        "mode": "MOCK/DEMO" if settings.demo_mode else "LIVE PROVIDERS",
    }
    logger.info(json.dumps({"event": "update_complete", **summary}))
    return summary
