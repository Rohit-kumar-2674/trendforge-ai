from datetime import UTC, datetime, timedelta

import pytest
from fastapi.testclient import TestClient
from pydantic import ValidationError
from sqlalchemy import func, select, text
from sqlalchemy.exc import IntegrityError

from trendforge.config import Settings
from trendforge.db import Entity, Forecast, Observation, Outcome, Score, UTCDateTime, migrate
from trendforge.forecasting.baseline import forecast
from trendforge.forecasting.registry import ensure_baseline
from trendforge.main import create_app
from trendforge.pipeline import (
    calculate_entity,
    digest,
    ingest,
    primary_history,
    purge_expired,
    resolve_outcomes,
)
from trendforge.providers.base import ProviderBatch
from trendforge.reports import generate_report
from trendforge.schemas import Domain, EntityInput, ObservationInput, utcnow
from trendforge.services import summary


def seed(session, settings, batch):
    ingest(session, batch)
    ensure_baseline(session)
    entity = session.get(Entity, "demo:test")
    calculate_entity(session, entity, settings)
    session.commit()
    return entity


def test_migrations_are_repeatable_and_match_schema(settings, session):
    migrate(settings.database_url)
    assert session.execute(text("SELECT version_num FROM alembic_version")).scalar() == "0002"
    assert session.scalar(select(func.count()).select_from(Entity)) == 0


def test_ingestion_is_idempotent_and_preserves_provenance(session, batch):
    first = ingest(session, batch)
    second = ingest(session, batch)
    assert first["inserted"] == 560
    assert second["inserted"] == 0
    assert second["duplicates"] == 560
    row = session.scalar(select(Observation))
    assert row.synthetic
    assert row.source_timestamp.tzinfo is not None
    assert row.retrieved_at >= row.source_timestamp


def test_snapshot_does_not_recompute_unchanged_history(session, settings, batch):
    entity = seed(session, settings, batch)
    count = session.scalar(select(func.count()).select_from(Forecast))
    assert count > 0
    assert not calculate_entity(session, entity, settings)
    assert session.scalar(select(func.count()).select_from(Forecast)) == count
    assert session.scalar(select(func.count()).select_from(Score)) == 1


def test_forecast_snapshot_is_reproducible(session, settings, batch):
    seed(session, settings, batch)
    item = session.scalar(select(Forecast))
    assert item.features_hash == digest(item.payload["feature_snapshot"])
    rebuilt = forecast(
        item.payload["input_snapshot"]["values"],
        item.horizon,
        synthetic=True,
        quality_score=item.payload["feature_snapshot"]["quality"]["score"],
    )
    assert rebuilt["probabilities"] == item.payload["probabilities"]
    assert item.issued_at > item.as_of
    assert len(item.payload["input_snapshot"]["timestamps"]) == 560


def test_forecasts_and_outcomes_cannot_be_overwritten(session, settings, batch):
    seed(session, settings, batch)
    item = session.scalar(select(Forecast))
    with pytest.raises(IntegrityError, match="append-only"):
        session.execute(text("UPDATE forecasts SET horizon = 99 WHERE id = :id"), {"id": item.id})
    session.rollback()
    with pytest.raises(IntegrityError, match="append-only"):
        session.execute(text("DELETE FROM forecasts WHERE id = :id"), {"id": item.id})
    session.rollback()


def test_old_backfill_does_not_issue_prospective_forecast(session, settings, batch):
    for row in batch.observations:
        row.source_timestamp -= timedelta(days=400)
    entity = seed(session, settings, batch)
    assert session.scalar(select(func.count()).select_from(Forecast)) == 0
    assert summary(session, entity)["freshness"]["status"] == "STALE"


def test_new_predictions_stay_pending_until_future_observed(session, settings, batch):
    seed(session, settings, batch)
    assert resolve_outcomes(session) == 0
    assert session.scalar(select(func.count()).select_from(Outcome)) == 0


def test_resolve_prospective_outcome_is_once_only(session, settings, batch):
    entity = seed(session, settings, batch)
    rows = primary_history(session, entity)
    # An intentionally constructed past issuance, before its target was observable.
    original = session.scalar(select(Forecast))
    origin = rows[-12]
    item = Forecast(
        id="prospective-test",
        entity_id=entity.id,
        issued_at=origin.source_timestamp + timedelta(hours=1),
        as_of=origin.source_timestamp,
        horizon=3,
        horizon_unit="calendar_day",
        target_metric="interest",
        target_provider="demo",
        model_version="audit-test-v1",
        snapshot_hash="test",
        features_hash="test",
        reference_value=origin.value,
        threshold=0.01,
        synthetic=True,
        payload=original.payload,
    )
    session.add(item)
    session.commit()
    assert resolve_outcomes(session) == 1
    session.commit()
    outcome = session.get(Outcome, item.id)
    assert outcome.actual_value == rows[-9].value
    assert outcome.observed_at > item.issued_at
    assert resolve_outcomes(session) == 0


def test_forecast_outcome_does_not_use_next_available_day(session, settings, batch):
    entity = seed(session, settings, batch)
    rows = primary_history(session, entity)
    source = rows[-10]
    original = session.scalar(select(Forecast))
    session.add(
        Forecast(
            id="missing-target",
            entity_id=entity.id,
            issued_at=source.source_timestamp + timedelta(hours=1),
            as_of=source.source_timestamp,
            horizon=3,
            horizon_unit="calendar_day",
            target_metric="interest",
            target_provider="demo",
            model_version="missing-v1",
            snapshot_hash="missing",
            features_hash="missing",
            reference_value=source.value,
            threshold=0.01,
            synthetic=True,
            payload=original.payload,
        )
    )
    session.delete(rows[-7])
    session.commit()
    resolve_outcomes(session)
    assert session.get(Outcome, "missing-target") is None


def test_timezone_validation_and_utc_roundtrip():
    with pytest.raises(ValidationError):
        ObservationInput(
            entity_id="x",
            provider="x",
            metric="interest",
            value=10,
            source_timestamp=datetime(2025, 1, 1),
        )
    row = ObservationInput(
        entity_id="x",
        provider="x",
        metric="interest",
        value=10,
        source_timestamp="2025-01-01T05:30:00+05:30",
    )
    assert row.source_timestamp.hour == 0
    assert row.source_timestamp.tzinfo == UTC
    with pytest.raises(ValueError):
        UTCDateTime().process_bind_param(datetime(2025, 1, 1), None)


@pytest.mark.parametrize("value", [float("nan"), float("inf"), -1])
def test_invalid_numbers_rejected(value):
    with pytest.raises(ValidationError):
        ObservationInput(
            entity_id="x", provider="x", metric="interest", value=value, source_timestamp=utcnow()
        )


def test_future_timestamp_and_unsafe_link_rejected():
    now = utcnow()
    with pytest.raises(ValidationError):
        ObservationInput(
            entity_id="x",
            provider="x",
            metric="interest",
            value=10,
            source_timestamp=now + timedelta(days=1),
            retrieved_at=now,
        )
    with pytest.raises(ValidationError):
        ObservationInput(
            entity_id="x",
            provider="x",
            metric="interest",
            value=10,
            source_timestamp=now,
            source_url="javascript:alert(1)",
        )


def test_youtube_retention_and_no_derived_analytics(session, settings):
    entity = EntityInput(
        id="youtube:abcdefghijk",
        name="Public video",
        domain=Domain.YOUTUBE,
        primary_metric="views",
        analytics_allowed=False,
    )
    old = utcnow() - timedelta(days=31)
    rows = [
        ObservationInput(
            entity_id=entity.id,
            provider="youtube",
            metric="views",
            value=20,
            source_timestamp=old,
            retrieved_at=old,
        )
    ]
    ingest(session, ProviderBatch(entities=[entity], observations=rows))
    assert not calculate_entity(session, session.get(Entity, entity.id), settings)
    assert purge_expired(session) == 1
    assert session.get(Entity, entity.id).name == "Unavailable YouTube video"


def test_api_routes_search_watchlist_audit_and_reports(session, settings, batch):
    seed(session, settings, batch)
    report = generate_report(session, settings)
    with TestClient(create_app(settings)) as client:
        assert client.get("/api/system/health").json()["mode"] == "MOCK/DEMO"
        assert client.get("/docs").status_code == 200
        assert "/api/trends/{entity_id}/forecast" in client.get("/openapi.json").json()["paths"]
        items = client.get("/api/trends?q=Synthetic").json()["items"]
        assert len(items) == 1
        assert client.get("/api/trends?q=' OR 1=1--").json()["items"] == []
        assert client.get("/api/trends/demo:test").json()["synthetic"]
        assert client.get("/api/trends/demo:test/history").json()["observations"]
        forecasts = client.get("/api/trends/demo:test/forecast").json()["items"]
        assert forecasts
        assert "input_snapshot" not in forecasts[0]
        assert (
            len(
                client.get(f"/api/forecasts/{forecasts[0]['id']}/audit").json()["input_snapshot"][
                    "values"
                ]
            )
            == 560
        )
        assert client.post("/api/watchlist", json={"entity_id": "demo:test"}).status_code == 201
        assert client.get("/api/watchlist").json()["items"][0]["id"] == "demo:test"
        assert client.delete("/api/watchlist/demo:test").status_code == 204
        assert client.get("/api/watchlist").json()["items"] == []
        assert client.get("/api/trends/missing").status_code == 404
        assert client.get("/api/trends/demo:test/evidence").json()["items"][0]["retrieved_at"]
        assert client.get("/api/models/track-record").json()["resolved"] == 0
        assert client.get(f"/api/reports/{report.id}?format=html").status_code == 200
        assert client.get(f"/api/reports/{report.id}?format=md").text.startswith("# TrendForge")
        assert client.get("/api/providers/status").status_code == 200
        assert client.get("/api/system/metrics").json()["observations"] == 560
        assert (
            client.post(
                "/api/experiments/backtest", json={"entity_id": "demo:test", "horizon": 7}
            ).json()["production_changed"]
            is False
        )
        assert (
            client.post(
                "/api/watchlist",
                json={"entity_id": "demo:test"},
                headers={"Origin": "https://untrusted.example"},
            ).status_code
            == 403
        )


def test_live_mode_requires_token(settings):
    settings.demo_mode = False
    with pytest.raises(RuntimeError, match="requires API_TOKEN"), TestClient(create_app(settings)):
        pass


def test_api_authentication_and_rate_limit(settings):
    secured = Settings(
        database_url=settings.database_url,
        demo_mode=False,
        api_token="test-access-only",
        request_limit_per_minute=3,
        _env_file=None,
    )
    with TestClient(create_app(secured)) as client:
        assert client.get("/api/trends").status_code == 401
        assert (
            client.get("/api/trends", headers={"Authorization": "Bearer wrong"}).status_code == 401
        )
        assert (
            client.get(
                "/api/trends", headers={"Authorization": "Bearer test-access-only"}
            ).status_code
            == 200
        )
        assert client.get("/api/system/health").status_code == 200
        assert client.get("/api/system/health").status_code == 200
        assert client.get("/api/system/health").status_code == 429


def test_report_files_are_timestamped_and_html_escaped(session, settings, batch):
    batch.entities[0].name = "<script>alert(1)</script>"
    seed(session, settings, batch)
    report = generate_report(session, settings)
    assert "<script>alert(1)</script>" not in report.html
    assert "&lt;script&gt;" in report.html
    assert "MOCK/DEMO" in report.markdown
    assert len(list(settings.reports_dir.glob("*.json"))) == 1
    assert len(list(settings.reports_dir.glob("*.html"))) == 1


def test_report_archive_does_not_mix_live_and_demo_modes(session, settings, batch):
    seed(session, settings, batch)
    demo_report = generate_report(session, settings)
    live_settings = settings.model_copy(update={"demo_mode": False})
    live_report = generate_report(session, live_settings)
    with TestClient(create_app(settings)) as client:
        assert [r["id"] for r in client.get("/api/reports").json()["items"]] == [demo_report.id]
        assert client.get(f"/api/reports/{live_report.id}").status_code == 404


def test_raw_only_video_statistics_never_enter_archival_reports(session, settings):
    from trendforge.schemas import Domain, EntityInput

    entity = EntityInput(
        id="youtube:abcdefghijk",
        name="Expiring public title",
        domain=Domain.YOUTUBE,
        primary_metric="views",
        analytics_allowed=False,
    )
    now = utcnow()
    row = ObservationInput(
        entity_id=entity.id,
        provider="youtube",
        metric="views",
        value=50,
        source_timestamp=now,
        retrieved_at=now,
    )
    ingest(session, ProviderBatch(entities=[entity], observations=[row]))
    session.commit()
    report = generate_report(session, settings.model_copy(update={"demo_mode": False}))
    assert all(not rows for rows in report.payload["sections"].values())
    assert "Expiring public title" not in report.markdown
