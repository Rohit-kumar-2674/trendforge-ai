import asyncio
import json
import logging
import platform
from typing import Any

import typer
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from trendforge import __version__
from trendforge.config import Settings
from trendforge.db import Entity, Forecast, ModelMetric, Observation, make_engine, migrate
from trendforge.forecasting.baseline import MODEL_VERSION, forecast
from trendforge.forecasting.ensemble import compare_models
from trendforge.forecasting.registry import ensure_baseline, promotion_decision
from trendforge.forecasting.validation import walk_forward
from trendforge.pipeline import digest, primary_history
from trendforge.pipeline import update as run_update
from trendforge.reports import generate_report
from trendforge.services import provider_status, track_record, trend_list

app = typer.Typer(
    no_args_is_help=True, help="TrendForge AI — Detect. Understand. Compare. Forecast."
)
logging.getLogger("httpx").setLevel(logging.WARNING)


def emit(value: Any) -> None:
    typer.echo(json.dumps(value, indent=2, default=str, allow_nan=False))


def session_for(settings: Settings) -> Session:
    migrate(settings.database_url)
    return Session(make_engine(settings.database_url), expire_on_commit=False)


@app.command()
def demo() -> None:
    """Build deterministic synthetic data, analysis, audit forecasts and a daily report."""
    settings = Settings(demo_mode=True)
    with session_for(settings) as session:
        result = asyncio.run(run_update(session, settings, force=True))
        report = generate_report(session, settings)
        emit(
            {
                **result,
                "report_id": report.id,
                "next": "trendforge serve, then start the frontend with npm run dev",
            }
        )
        if result["analysis_failures"]:
            raise typer.Exit(1)


@app.command()
def update(
    force: bool = typer.Option(
        False, help="Bypass the 24-hour ingestion cache; still honor provider quotas"
    ),
) -> None:
    """Refresh configured providers, retaining cached history when a source fails."""
    settings = Settings()
    with session_for(settings) as session:
        result = asyncio.run(run_update(session, settings, force=force))
        generate_report(session, settings)
        emit(result)
        if result["analysis_failures"]:
            raise typer.Exit(1)


@app.command()
def report() -> None:
    """Write timestamped Markdown, JSON and HTML reports."""
    settings = Settings()
    with session_for(settings) as session:
        result = generate_report(session, settings)
        emit(
            {"id": result.id, "directory": str(settings.reports_dir.resolve()), "mode": result.mode}
        )


@app.command()
def search(query: str) -> None:
    """Search the local canonical entity catalogue; does not invent unconfigured data."""
    settings = Settings()
    with session_for(settings) as session:
        emit(trend_list(session, settings, q=query))


@app.command()
def trend(query: str) -> None:
    """Inspect a trend and its stored evidence/forecast."""
    search(query)


@app.command()
def stock(ticker: str) -> None:
    """Inspect a configured stock; use ORBT in demo mode."""
    settings = Settings()
    with session_for(settings) as session:
        emit(trend_list(session, settings, q=ticker, domain="stocks"))


@app.command()
def emerging() -> None:
    """Rank early signals using the transparent heuristic score."""
    settings = Settings()
    with session_for(settings) as session:
        emit(trend_list(session, settings, sort="emerging"))


@app.command()
def providers() -> None:
    """Show provider health and configuration requirements, never secrets."""
    settings = Settings()
    with session_for(settings) as session:
        emit(provider_status(session, settings))


@app.command()
def doctor() -> None:
    """Check the runtime, schema, dataset and providers."""
    settings = Settings()
    with session_for(settings) as session:
        emit(
            {
                "version": __version__,
                "python": platform.python_version(),
                "platform": platform.system(),
                "database": "SQLite"
                if settings.database_url.startswith("sqlite")
                else "SQL database",
                "mode": "MOCK/DEMO" if settings.demo_mode else "LIVE PROVIDERS",
                "entities": session.scalar(select(func.count()).select_from(Entity)),
                "observations": session.scalar(select(func.count()).select_from(Observation)),
                "api_token_configured": bool(settings.api_token.get_secret_value()),
                "providers": provider_status(session, settings),
            }
        )


@app.command()
def serve(host: str = "127.0.0.1", port: int = 8000) -> None:
    """Start the API; migrations run automatically, ingestion stays outside the server."""
    import uvicorn

    uvicorn.run("trendforge.main:app", host=host, port=port, proxy_headers=False)


@app.command()
def evaluate(
    entity_id: str = "demo:smart-glasses", horizon: int = 7, ensemble: bool = False
) -> None:
    """Run retrospective research; append the result, never replace a production model."""
    settings = Settings()
    with session_for(settings) as session:
        entity = session.get(Entity, entity_id)
        if entity is None or entity.synthetic != settings.demo_mode or not entity.analytics_allowed:
            raise typer.BadParameter("No eligible entity in the active data mode")
        if horizon < 1 or horizon > 90:
            raise typer.BadParameter("Horizon must be 1–90")
        values = [r.value for r in primary_history(session, entity)]
        result = compare_models(values, horizon) if ensemble else walk_forward(values, horizon)
        ensure_baseline(session)
        session.flush()
        session.add(
            ModelMetric(
                model_version=MODEL_VERSION,
                payload={
                    "entity_id": entity_id,
                    "synthetic": entity.synthetic,
                    "kind": "research_ensemble" if ensemble else "retrospective_baseline",
                    "result": result,
                },
            )
        )
        session.commit()
        emit(
            {
                "entity_id": entity_id,
                "synthetic": entity.synthetic,
                "result": result,
                "promotion": promotion_decision(
                    {"synthetic": entity.synthetic, "prospective": False}, {}
                ),
            }
        )


@app.command(name="track-record")
def record() -> None:
    """Show prospective performance and pending forecasts."""
    settings = Settings()
    with session_for(settings) as session:
        emit(track_record(session, settings))


@app.command(name="verify-audit")
def verify_audit(forecast_id: str) -> None:
    """Recompute a stored forecast from its frozen snapshot and compare hashes."""
    settings = Settings()
    with session_for(settings) as session:
        item = session.get(Forecast, forecast_id)
        if item is None:
            raise typer.BadParameter("Unknown forecast ID")
        features_match = digest(item.payload["feature_snapshot"]) == item.features_hash
        rebuilt = forecast(
            item.payload["input_snapshot"]["values"],
            item.horizon,
            synthetic=item.synthetic,
            quality_score=item.payload["feature_snapshot"]["quality"]["score"],
        )
        prediction_matches = rebuilt["probabilities"] == item.payload["probabilities"]
        emit(
            {
                "forecast_id": forecast_id,
                "features_hash_matches": features_match,
                "probabilities_match": prediction_matches,
                "model_version": item.model_version,
            }
        )
        if not features_match or not prediction_matches:
            raise typer.Exit(1)
