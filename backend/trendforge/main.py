import hmac
import time
from collections import defaultdict, deque
from collections.abc import AsyncIterator, Iterator
from contextlib import asynccontextmanager
from typing import Any

import pandas as pd
from fastapi import Depends, FastAPI, HTTPException, Query, Request, Response
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import HTMLResponse, JSONResponse, PlainTextResponse
from sqlalchemy import func, select, text
from sqlalchemy.orm import Session, sessionmaker

from trendforge import __version__
from trendforge.config import Settings, get_settings
from trendforge.db import (
    Entity,
    Event,
    Forecast,
    ModelVersion,
    Observation,
    Outcome,
    Report,
    Score,
    Watchlist,
    make_engine,
    migrate,
)
from trendforge.forecasting.validation import walk_forward
from trendforge.pipeline import primary_history, purge_expired
from trendforge.reports import report_mode
from trendforge.schemas import ExperimentInput, WatchlistInput, utcnow
from trendforge.services import (
    DISCLAIMER,
    compact_forecast,
    events,
    observations,
    provider_status,
    summary,
    track_record,
    trend_list,
)
from trendforge.trends.relationships import lead_lag


def create_app(settings: Settings | None = None) -> FastAPI:
    config = settings or get_settings()
    engine = make_engine(config.database_url)
    factory = sessionmaker(engine, expire_on_commit=False)

    @asynccontextmanager
    async def lifespan(app: FastAPI) -> AsyncIterator[None]:
        if not config.demo_mode and not config.api_token.get_secret_value():
            raise RuntimeError(
                "Live mode requires API_TOKEN. Set a strong token in your server environment."
            )
        migrate(config.database_url)
        with factory() as session:
            purge_expired(session)
            session.commit()
        yield
        engine.dispose()

    app = FastAPI(
        title="TrendForge AI", version=__version__, description=DISCLAIMER, lifespan=lifespan
    )
    app.state.engine = engine
    app.add_middleware(
        CORSMiddleware,
        allow_origins=config.cors_origins.split(","),
        allow_methods=["GET", "POST", "DELETE"],
        allow_headers=["Authorization", "Content-Type"],
    )
    requests: dict[str, deque[float]] = defaultdict(deque)

    @app.middleware("http")
    async def guard(request: Request, call_next: Any) -> Response:
        token = config.api_token.get_secret_value()
        if (
            token
            and request.url.path.startswith("/api/")
            and request.url.path != "/api/system/health"
            and request.method != "OPTIONS"
        ):
            supplied = request.headers.get("Authorization", "").removeprefix("Bearer ")
            if not hmac.compare_digest(supplied, token):
                return JSONResponse({"detail": "An API access token is required"}, status_code=401)
        now = time.monotonic()
        # Do not trust X-Forwarded-For from arbitrary clients.
        host = request.client.host if request.client else "unknown"
        bucket = requests[host]
        while bucket and now - bucket[0] > 60:
            bucket.popleft()
        if len(bucket) >= config.request_limit_per_minute:
            return JSONResponse(
                {"detail": "Request limit reached"}, status_code=429, headers={"Retry-After": "60"}
            )
        bucket.append(now)
        if len(requests) > 10000:
            expired = [key for key, q in requests.items() if not q or now - q[-1] > 60]
            for key in expired:
                requests.pop(key, None)
        origin = request.headers.get("origin")
        if (
            request.method in ("POST", "DELETE")
            and origin
            and origin not in config.cors_origins.split(",")
        ):
            return JSONResponse({"detail": "Origin is not allowed"}, status_code=403)
        response = await call_next(request)
        response.headers.update(
            {
                "X-Content-Type-Options": "nosniff",
                "X-Frame-Options": "DENY",
                "Referrer-Policy": "strict-origin-when-cross-origin",
                "Cache-Control": "no-store",
            }
        )
        return response

    def db_session() -> Iterator[Session]:
        with factory() as session:
            yield session

    def entity_or_404(session: Session, entity_id: str) -> Entity:
        entity = session.get(Entity, entity_id)
        if entity is None or entity.synthetic != config.demo_mode:
            raise HTTPException(404, "Trend not found in the active data mode")
        return entity

    @app.get("/api/system/health")
    def health(session: Session = Depends(db_session)) -> dict[str, Any]:
        session.execute(text("SELECT 1"))
        return {
            "status": "ok",
            "version": __version__,
            "database": "reachable",
            "mode": "MOCK/DEMO" if config.demo_mode else "LIVE PROVIDERS",
            "timezone": "UTC",
            "now": utcnow().isoformat(),
            "disclaimer": DISCLAIMER,
        }

    @app.get("/api/trends")
    def trends(
        q: str = Query("", max_length=200),
        domain: str = "",
        region: str = "",
        sort: str = Query(
            "score", pattern="^(score|momentum|acceleration|emerging|cooling|volatility)$"
        ),
        session: Session = Depends(db_session),
    ) -> dict[str, Any]:
        return {
            "items": trend_list(session, config, q=q, domain=domain, region=region, sort=sort),
            "mode": "MOCK/DEMO" if config.demo_mode else "LIVE PROVIDERS",
        }

    @app.get("/api/trends/emerging")
    def emerging(session: Session = Depends(db_session)) -> dict[str, Any]:
        return {"items": trend_list(session, config, sort="emerging")}

    @app.get("/api/trends/accelerating")
    def accelerating(session: Session = Depends(db_session)) -> dict[str, Any]:
        return {"items": trend_list(session, config, sort="acceleration")}

    @app.get("/api/trends/{entity_id}")
    def detail(entity_id: str, session: Session = Depends(db_session)) -> dict[str, Any]:
        entity = entity_or_404(session, entity_id)
        result = summary(session, entity)
        timeline = session.scalars(
            select(Event).where(Event.entity_id == entity.id).order_by(Event.occurred_at.desc())
        )
        result["timeline"] = [
            {"occurred_at": e.occurred_at.isoformat(), "kind": e.kind, **e.payload}
            for e in timeline
        ]
        return result

    @app.get("/api/trends/{entity_id}/history")
    def history(
        entity_id: str,
        limit: int = Query(600, ge=10, le=2000),
        session: Session = Depends(db_session),
    ) -> dict[str, Any]:
        entity = entity_or_404(session, entity_id)
        rows = primary_history(session, entity)
        scores = session.scalars(
            select(Score).where(Score.entity_id == entity.id).order_by(Score.as_of)
        )
        return {
            "observations": [
                {
                    "date": r.source_timestamp.isoformat(),
                    "value": r.value,
                    "provider": r.provider,
                    "retrieved_at": r.retrieved_at.isoformat(),
                    "unit": r.unit,
                    "synthetic": r.synthetic,
                }
                for r in rows[-limit:]
            ],
            "scores": [
                {
                    "date": s.as_of.isoformat(),
                    "score": s.payload["current_score"],
                    "momentum": s.payload["components"]["momentum"],
                    "acceleration": s.payload["relative_acceleration"],
                }
                for s in scores
            ],
            "timezone": "UTC",
            "metric": entity.primary_metric,
            "unit": entity.unit,
        }

    @app.get("/api/trends/{entity_id}/forecast")
    def forecasts(
        entity_id: str,
        horizon: int | None = Query(None, ge=1, le=90),
        session: Session = Depends(db_session),
    ) -> dict[str, Any]:
        entity_or_404(session, entity_id)
        query = (
            select(Forecast)
            .where(Forecast.entity_id == entity_id)
            .order_by(Forecast.issued_at.desc())
        )
        if horizon:
            query = query.where(Forecast.horizon == horizon)
        items = [
            compact_forecast(f, session.get(Outcome, f.id))
            for f in session.scalars(query.limit(100))
        ]
        return {
            "items": items,
            "note": "Stored forecasts, never recomputed on read; pending outcomes remain pending.",
        }

    @app.get("/api/trends/{entity_id}/analogues")
    def analogues(entity_id: str, session: Session = Depends(db_session)) -> dict[str, Any]:
        entity = entity_or_404(session, entity_id)
        result = summary(session, entity)["forecast"]
        return {
            "items": result["analogues"] if result else [],
            "caution": "Historical similarity does not guarantee the future.",
        }

    @app.get("/api/trends/{entity_id}/evidence")
    def evidence(
        entity_id: str,
        limit: int = Query(300, ge=1, le=2000),
        session: Session = Depends(db_session),
    ) -> dict[str, Any]:
        entity = entity_or_404(session, entity_id)
        return {"items": observations(session, entity, limit)}

    @app.get("/api/forecasts/{forecast_id}/audit")
    def audit(forecast_id: str, session: Session = Depends(db_session)) -> dict[str, Any]:
        item = session.get(Forecast, forecast_id)
        if item is None or item.synthetic != config.demo_mode:
            raise HTTPException(404, "Forecast not found")
        return {
            **compact_forecast(item, session.get(Outcome, item.id)),
            "input_snapshot": item.payload["input_snapshot"],
            "feature_snapshot": item.payload["feature_snapshot"],
        }

    @app.get("/api/stocks/{ticker}")
    def stock(ticker: str, session: Session = Depends(db_session)) -> dict[str, Any]:
        found = trend_list(session, config, q=ticker, domain="stocks")
        if not found:
            raise HTTPException(404, "No configured stock matches this ticker")
        return found[0]

    @app.get("/api/stocks/{ticker}/forecast")
    def stock_forecast(ticker: str, session: Session = Depends(db_session)) -> dict[str, Any]:
        item = stock(ticker, session)
        return forecasts(item["id"], None, session)

    @app.get("/api/youtube/topics")
    def youtube(session: Session = Depends(db_session)) -> dict[str, Any]:
        return {
            "items": trend_list(session, config, domain="youtube"),
            "note": "Live API data is raw-only. Synthetic topics demonstrate custom analytics.",
        }

    @app.get("/api/search/topics")
    def search_topics(session: Session = Depends(db_session)) -> dict[str, Any]:
        return {
            "items": trend_list(session, config, domain="search"),
            "capability": "MOCK/DEMO" if config.demo_mode else "NOT CONFIGURED",
        }

    @app.get("/api/watchlist")
    def watchlist(session: Session = Depends(db_session)) -> dict[str, Any]:
        return {
            "items": trend_list(session, config, watchlist=True),
            "scope": "Single local workspace; not a multi-user account system",
        }

    @app.post("/api/watchlist", status_code=201)
    def add_watchlist(
        body: WatchlistInput, session: Session = Depends(db_session)
    ) -> dict[str, str]:
        entity_or_404(session, body.entity_id)
        if session.get(Watchlist, body.entity_id) is None:
            session.add(Watchlist(entity_id=body.entity_id))
            session.commit()
        return {"status": "saved", "entity_id": body.entity_id}

    @app.delete("/api/watchlist/{entity_id}", status_code=204)
    def remove_watchlist(entity_id: str, session: Session = Depends(db_session)) -> Response:
        entity_or_404(session, entity_id)
        row = session.get(Watchlist, entity_id)
        if row:
            session.delete(row)
            session.commit()
        return Response(status_code=204)

    @app.get("/api/providers/status")
    def status(session: Session = Depends(db_session)) -> dict[str, Any]:
        return {"items": provider_status(session, config)}

    @app.get("/api/events")
    def alerts(session: Session = Depends(db_session)) -> dict[str, Any]:
        return {"items": events(session, config)}

    @app.get("/api/models")
    def models(session: Session = Depends(db_session)) -> dict[str, Any]:
        return {
            "items": [
                {
                    "id": m.id,
                    "status": m.status,
                    "created_at": m.created_at.isoformat(),
                    "card": m.card,
                }
                for m in session.scalars(select(ModelVersion))
            ]
        }

    @app.get("/api/models/track-record")
    def record(session: Session = Depends(db_session)) -> dict[str, Any]:
        return track_record(session, config)

    @app.get("/api/relationships")
    def relationships(
        left: str,
        right: str,
        max_lag: int = Query(14, ge=0, le=30),
        session: Session = Depends(db_session),
    ) -> dict[str, Any]:
        a, b = entity_or_404(session, left), entity_or_404(session, right)
        if not a.analytics_allowed or not b.analytics_allowed:
            raise HTTPException(409, "Derived analytics are not enabled for these sources")

        def series(entity: Entity) -> pd.Series:
            rows = primary_history(session, entity)
            return pd.Series(
                [r.value for r in rows],
                index=pd.DatetimeIndex([r.source_timestamp.date() for r in rows]),
                dtype=float,
            )

        return {"left": a.name, "right": b.name, **lead_lag(series(a), series(b), max_lag)}

    @app.post("/api/experiments/backtest")
    def backtest(body: ExperimentInput, session: Session = Depends(db_session)) -> dict[str, Any]:
        entity = entity_or_404(session, body.entity_id)
        if not entity.analytics_allowed:
            raise HTTPException(409, "Derived analytics disabled for this source")
        if body.method == "dtw":
            raise HTTPException(422, "Use the CLI for expensive DTW research runs")
        values = [r.value for r in primary_history(session, entity)][-800:]
        return {
            "entity": entity.name,
            "synthetic": entity.synthetic,
            "production_changed": False,
            **walk_forward(values, body.horizon, method=body.method, window=body.window),
        }

    @app.get("/api/reports")
    def reports(session: Session = Depends(db_session)) -> dict[str, Any]:
        return {
            "items": [
                {"id": r.id, "created_at": r.created_at.isoformat(), "mode": r.mode}
                for r in session.scalars(
                    select(Report)
                    .where(Report.mode == report_mode(config.demo_mode))
                    .order_by(Report.created_at.desc())
                    .limit(60)
                )
            ]
        }

    @app.get("/api/reports/{report_id}")
    def report(
        report_id: str,
        format: str = Query("json", pattern="^(json|md|html)$"),
        session: Session = Depends(db_session),
    ) -> Any:
        item = session.get(Report, report_id)
        if item is None or item.mode != report_mode(config.demo_mode):
            raise HTTPException(404, "Report not found in the active data mode")
        if format == "md":
            return PlainTextResponse(item.markdown)
        if format == "html":
            return HTMLResponse(item.html)
        return item.payload

    @app.get("/api/system/metrics")
    def system_metrics(session: Session = Depends(db_session)) -> dict[str, Any]:
        return {
            "observations": session.scalar(select(func.count()).select_from(Observation)),
            "forecasts": session.scalar(select(func.count()).select_from(Forecast)),
            "providers": provider_status(session, config),
        }

    return app


app = create_app()
