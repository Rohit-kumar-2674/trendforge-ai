from typing import Any

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from trendforge.config import Settings
from trendforge.db import (
    Entity,
    Event,
    Forecast,
    Observation,
    Outcome,
    ProviderState,
    Score,
    Watchlist,
)
from trendforge.forecasting.validation import metrics
from trendforge.pipeline import primary_history
from trendforge.schemas import utcnow
from trendforge.trends.quality import freshness

DISCLAIMER = "TrendForge provides statistical, historical and informational analysis. Forecasts are probabilistic estimates derived from available data and models and may be incorrect. Financial-market information is provided for research and educational purposes and is not personalized investment advice."


def compact_forecast(item: Forecast, outcome: Outcome | None = None) -> dict[str, Any]:
    payload = {
        k: v for k, v in item.payload.items() if k not in ("input_snapshot", "feature_snapshot")
    }
    return {
        "id": item.id,
        "entity_id": item.entity_id,
        "issued_at": item.issued_at.isoformat(),
        "as_of": item.as_of.isoformat(),
        "features_hash": item.features_hash,
        **payload,
        "outcome": {
            "actual_class": outcome.actual_class,
            "actual_return": outcome.actual_return,
            "observed_at": outcome.observed_at.isoformat(),
            "evaluated_at": outcome.evaluated_at.isoformat(),
            "correct": outcome.correct,
        }
        if outcome
        else None,
    }


def summary(session: Session, entity: Entity) -> dict[str, Any]:
    latest = session.scalar(
        select(Score)
        .where(Score.entity_id == entity.id)
        .order_by(Score.as_of.desc(), Score.id.desc())
    )
    rows = primary_history(session, entity)
    last = rows[-1] if rows else None
    generated = list(
        session.scalars(
            select(Forecast)
            .where(Forecast.entity_id == entity.id)
            .order_by(Forecast.issued_at.desc())
        )
    )
    predictions: dict[int, Forecast] = {}
    for item in generated:
        if item.horizon not in predictions:
            predictions[item.horizon] = item
    favored = predictions.get(5 if entity.domain in ("stocks", "crypto") else 7)
    selected = favored or next(iter(predictions.values()), None)
    payload = latest.payload if latest else {}
    return {
        "id": entity.id,
        "name": entity.name,
        "domain": entity.domain,
        "category": entity.category,
        "region": entity.region,
        "keywords": entity.keywords,
        "unit": entity.unit,
        "cadence": entity.cadence,
        "primary_metric": entity.primary_metric,
        "synthetic": entity.synthetic,
        "analytics_allowed": entity.analytics_allowed,
        "first_seen": entity.first_seen.isoformat(),
        "last_updated": last.source_timestamp.isoformat() if last else None,
        "freshness": freshness(
            last.source_timestamp if last else None,
            last.retrieved_at if last else None,
            utcnow(),
            72 if entity.cadence == "trading_session" else 24,
        ),
        "score": payload,
        "sparkline": [
            {"date": row.source_timestamp.isoformat(), "value": row.value} for row in rows[-45:]
        ],
        "forecast": compact_forecast(selected, session.get(Outcome, selected.id))
        if selected
        else None,
        "forecast_status": "RAW STATISTICS ONLY"
        if not entity.analytics_allowed
        else "AVAILABLE"
        if selected
        else "INSUFFICIENT HISTORY OR STALE DATA",
        "watchlisted": session.get(Watchlist, entity.id) is not None,
    }


def trend_list(
    session: Session,
    settings: Settings,
    *,
    q: str = "",
    domain: str = "",
    region: str = "",
    sort: str = "score",
    watchlist: bool = False,
) -> list[dict[str, Any]]:
    query = select(Entity).where(Entity.synthetic == settings.demo_mode)
    if domain:
        query = query.where(Entity.domain == domain)
    if region:
        query = query.where(Entity.region == region)
    if watchlist:
        query = query.join(Watchlist, Watchlist.entity_id == Entity.id)
    candidates = list(session.scalars(query.order_by(Entity.name)))
    if q:
        needle = q.casefold()
        candidates = [
            e
            for e in candidates
            if needle in " ".join([e.id, e.name, e.category, *e.keywords]).casefold()
        ]
    result = [summary(session, entity) for entity in candidates]
    field = {
        "score": "current_score",
        "momentum": "momentum",
        "acceleration": "relative_acceleration",
        "emerging": "early_signal_score",
        "cooling": "growth_7_periods",
        "volatility": "volatility",
    }.get(sort, "current_score")
    result.sort(
        key=lambda e: (
            e["score"].get("components", {}).get(field, 0)
            if field == "momentum"
            else e["score"].get(field, 0)
        ),
        reverse=sort != "cooling",
    )
    return result


def provider_status(session: Session, settings: Settings) -> list[dict[str, Any]]:
    from trendforge.providers import providers

    output = []
    for adapter in providers(settings):
        item = session.get(ProviderState, adapter.name)
        status = item.status if item else "NOT CONFIGURED" if not adapter.configured else "OFFLINE"
        if (
            item
            and item.last_success
            and status == "ONLINE"
            and (utcnow() - item.last_success).total_seconds()
            > item.expected_interval_hours * 3600 * 3
        ):
            status = "STALE"
        output.append(
            {
                "name": adapter.name,
                "status": status,
                "capability": adapter.capability,
                "message": item.message if item else adapter.instructions,
                "last_success": item.last_success.isoformat()
                if item and item.last_success
                else None,
                "last_attempt": item.last_attempt.isoformat()
                if item and item.last_attempt
                else None,
                "expected_interval_hours": adapter.expected_interval_hours,
                "records": item.records if item else 0,
                "stats": item.stats if item else {},
            }
        )
    return output


def track_record(session: Session, settings: Settings) -> dict[str, Any]:
    pairs = session.execute(
        select(Forecast, Outcome)
        .join(Outcome, Outcome.forecast_id == Forecast.id)
        .where(Forecast.synthetic == settings.demo_mode)
    ).all()
    count = (
        session.scalar(
            select(func.count())
            .select_from(Forecast)
            .where(Forecast.synthetic == settings.demo_mode)
        )
        or 0
    )

    def measure(rows: list[Any]) -> dict[str, Any]:
        return metrics(
            [o.actual_class for _, o in rows], [f.payload["probabilities"] for f, _ in rows]
        )

    buckets: dict[str, dict[str, Any]] = {}
    for field in ("horizon", "confidence", "regime"):
        grouped: dict[str, list[Any]] = {}
        for f, o in pairs:
            value = (
                str(f.horizon)
                if field == "horizon"
                else f.payload.get("confidence", "Unknown")
                if field == "confidence"
                else f.payload.get("feature_snapshot", {})
                .get("technicals", {})
                .get("regime", "Non-financial")
            )
            grouped.setdefault(value, []).append((f, o))
        buckets[field] = {name: measure(rows) for name, rows in grouped.items()}
    return {
        "issued": count,
        "resolved": len(pairs),
        "pending": count - len(pairs),
        "synthetic": settings.demo_mode,
        "metrics": measure(list(pairs)),
        "by": buckets,
        "note": "Prospective, append-only forecast ledger. Empty outcomes are expected until future observations arrive. Demo accuracy is not real-world performance.",
    }


def events(session: Session, settings: Settings) -> list[dict[str, Any]]:
    rows = session.execute(
        select(Event, Entity.name)
        .join(Entity, Event.entity_id == Entity.id)
        .where(Entity.synthetic == settings.demo_mode)
        .order_by(Event.occurred_at.desc())
        .limit(100)
    ).all()
    return [
        {
            "id": e.id,
            "entity_id": e.entity_id,
            "name": name,
            "occurred_at": e.occurred_at.isoformat(),
            "kind": e.kind,
            **e.payload,
        }
        for e, name in rows
    ]


def observations(session: Session, entity: Entity, limit: int = 600) -> list[dict[str, Any]]:
    query = select(Observation).where(Observation.entity_id == entity.id)
    if entity.id.startswith("youtube:"):
        from datetime import timedelta

        query = query.where(Observation.retrieved_at >= utcnow() - timedelta(days=29))
    rows = session.scalars(
        query.order_by(Observation.source_timestamp.desc(), Observation.metric).limit(limit)
    )
    return [
        {
            "id": row.id,
            "metric": row.metric,
            "value": row.value,
            "provider": row.provider,
            "source_timestamp": row.source_timestamp.isoformat(),
            "retrieved_at": row.retrieved_at.isoformat(),
            "source_url": row.source_url,
            "unit": row.unit,
            "synthetic": row.synthetic,
            "metadata": row.detail,
        }
        for row in rows
    ]
