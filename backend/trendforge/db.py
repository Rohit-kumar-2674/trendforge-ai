from collections.abc import Iterator
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from sqlalchemy import (
    JSON,
    Boolean,
    DateTime,
    Float,
    ForeignKey,
    Integer,
    String,
    UniqueConstraint,
    create_engine,
    event,
)
from sqlalchemy.engine import Engine
from sqlalchemy.orm import DeclarativeBase, Mapped, Session, mapped_column, sessionmaker
from sqlalchemy.types import TypeDecorator

from trendforge.schemas import utcnow


class UTCDateTime(TypeDecorator[datetime]):
    impl = DateTime(timezone=True)
    cache_ok = True

    def process_bind_param(self, value: datetime | None, dialect: Any) -> datetime | None:
        if value is not None:
            if value.tzinfo is None:
                raise ValueError("Naive database timestamp")
            return value.astimezone(UTC)
        return None

    def process_result_value(self, value: datetime | None, dialect: Any) -> datetime | None:
        return value.replace(tzinfo=UTC) if value and value.tzinfo is None else value


class Base(DeclarativeBase):
    pass


class Entity(Base):
    __tablename__ = "entities"
    id: Mapped[str] = mapped_column(String(150), primary_key=True)
    name: Mapped[str] = mapped_column(String(200), index=True)
    domain: Mapped[str] = mapped_column(String(30), index=True)
    category: Mapped[str] = mapped_column(String(100), default="")
    region: Mapped[str] = mapped_column(String(30), default="GLOBAL")
    keywords: Mapped[list[str]] = mapped_column(JSON, default=list)
    primary_metric: Mapped[str] = mapped_column(String(60))
    unit: Mapped[str] = mapped_column(String(40))
    cadence: Mapped[str] = mapped_column(String(30), default="calendar_day")
    synthetic: Mapped[bool] = mapped_column(Boolean, default=False)
    analytics_allowed: Mapped[bool] = mapped_column(Boolean, default=True)
    first_seen: Mapped[datetime] = mapped_column(UTCDateTime, default=utcnow)


class Observation(Base):
    __tablename__ = "trend_observations"
    __table_args__ = (
        UniqueConstraint(
            "entity_id", "provider", "metric", "source_timestamp", name="uq_observation"
        ),
    )
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    entity_id: Mapped[str] = mapped_column(ForeignKey("entities.id"), index=True)
    provider: Mapped[str] = mapped_column(String(80), index=True)
    metric: Mapped[str] = mapped_column(String(60))
    value: Mapped[float] = mapped_column(Float)
    source_timestamp: Mapped[datetime] = mapped_column(UTCDateTime, index=True)
    retrieved_at: Mapped[datetime] = mapped_column(UTCDateTime)
    unit: Mapped[str] = mapped_column(String(40))
    source_url: Mapped[str | None] = mapped_column(String(1000))
    synthetic: Mapped[bool] = mapped_column(Boolean)
    detail: Mapped[dict[str, Any]] = mapped_column(JSON, default=dict)


class Score(Base):
    __tablename__ = "trend_scores"
    __table_args__ = (UniqueConstraint("entity_id", "snapshot_hash", name="uq_score_snapshot"),)
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    entity_id: Mapped[str] = mapped_column(ForeignKey("entities.id"), index=True)
    as_of: Mapped[datetime] = mapped_column(UTCDateTime, index=True)
    calculated_at: Mapped[datetime] = mapped_column(UTCDateTime, default=utcnow)
    snapshot_hash: Mapped[str] = mapped_column(String(64))
    payload: Mapped[dict[str, Any]] = mapped_column(JSON)


class Forecast(Base):
    __tablename__ = "forecasts"
    __table_args__ = (
        UniqueConstraint(
            "entity_id", "snapshot_hash", "horizon", "model_version", name="uq_forecast_snapshot"
        ),
    )
    id: Mapped[str] = mapped_column(String(40), primary_key=True)
    entity_id: Mapped[str] = mapped_column(ForeignKey("entities.id"), index=True)
    issued_at: Mapped[datetime] = mapped_column(UTCDateTime, default=utcnow, index=True)
    as_of: Mapped[datetime] = mapped_column(UTCDateTime)
    horizon: Mapped[int] = mapped_column(Integer)
    horizon_unit: Mapped[str] = mapped_column(String(30))
    target_metric: Mapped[str] = mapped_column(String(60))
    target_provider: Mapped[str] = mapped_column(String(80))
    model_version: Mapped[str] = mapped_column(String(80))
    snapshot_hash: Mapped[str] = mapped_column(String(64))
    features_hash: Mapped[str] = mapped_column(String(64))
    reference_value: Mapped[float] = mapped_column(Float)
    threshold: Mapped[float] = mapped_column(Float)
    synthetic: Mapped[bool] = mapped_column(Boolean)
    payload: Mapped[dict[str, Any]] = mapped_column(JSON)


class Outcome(Base):
    __tablename__ = "forecast_outcomes"
    forecast_id: Mapped[str] = mapped_column(ForeignKey("forecasts.id"), primary_key=True)
    observed_at: Mapped[datetime] = mapped_column(UTCDateTime)
    evaluated_at: Mapped[datetime] = mapped_column(UTCDateTime, default=utcnow)
    actual_value: Mapped[float] = mapped_column(Float)
    actual_return: Mapped[float] = mapped_column(Float)
    actual_class: Mapped[str] = mapped_column(String(20))
    correct: Mapped[bool] = mapped_column(Boolean)


class ProviderState(Base):
    __tablename__ = "providers"
    name: Mapped[str] = mapped_column(String(80), primary_key=True)
    status: Mapped[str] = mapped_column(String(30))
    capability: Mapped[str] = mapped_column(String(30))
    message: Mapped[str] = mapped_column(String(600))
    last_attempt: Mapped[datetime | None] = mapped_column(UTCDateTime)
    last_success: Mapped[datetime | None] = mapped_column(UTCDateTime)
    expected_interval_hours: Mapped[int] = mapped_column(Integer, default=24)
    records: Mapped[int] = mapped_column(Integer, default=0)
    stats: Mapped[dict[str, Any]] = mapped_column(JSON, default=dict)


class Watchlist(Base):
    __tablename__ = "watchlists"
    entity_id: Mapped[str] = mapped_column(ForeignKey("entities.id"), primary_key=True)
    added_at: Mapped[datetime] = mapped_column(UTCDateTime, default=utcnow)


class Report(Base):
    __tablename__ = "daily_reports"
    id: Mapped[str] = mapped_column(String(40), primary_key=True)
    created_at: Mapped[datetime] = mapped_column(UTCDateTime, default=utcnow)
    mode: Mapped[str] = mapped_column(String(80))
    payload: Mapped[dict[str, Any]] = mapped_column(JSON)
    markdown: Mapped[str] = mapped_column(String)
    html: Mapped[str] = mapped_column(String)


class ModelVersion(Base):
    __tablename__ = "model_versions"
    id: Mapped[str] = mapped_column(String(80), primary_key=True)
    created_at: Mapped[datetime] = mapped_column(UTCDateTime, default=utcnow)
    status: Mapped[str] = mapped_column(String(30))
    card: Mapped[dict[str, Any]] = mapped_column(JSON)


class ModelMetric(Base):
    __tablename__ = "model_metrics"
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    model_version: Mapped[str] = mapped_column(ForeignKey("model_versions.id"))
    measured_at: Mapped[datetime] = mapped_column(UTCDateTime, default=utcnow)
    payload: Mapped[dict[str, Any]] = mapped_column(JSON)


class Event(Base):
    __tablename__ = "events"
    id: Mapped[str] = mapped_column(String(80), primary_key=True)
    entity_id: Mapped[str] = mapped_column(ForeignKey("entities.id"), index=True)
    occurred_at: Mapped[datetime] = mapped_column(UTCDateTime)
    kind: Mapped[str] = mapped_column(String(40))
    payload: Mapped[dict[str, Any]] = mapped_column(JSON)


class Relationship(Base):
    __tablename__ = "relationships"
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    source_id: Mapped[str] = mapped_column(ForeignKey("entities.id"))
    target_id: Mapped[str] = mapped_column(ForeignKey("entities.id"))
    kind: Mapped[str] = mapped_column(String(40))
    measured_at: Mapped[datetime] = mapped_column(UTCDateTime, default=utcnow)
    payload: Mapped[dict[str, Any]] = mapped_column(JSON)


def make_engine(url: str) -> Engine:
    if url.startswith("sqlite:///") and ":memory:" not in url:
        Path(url.removeprefix("sqlite:///")).parent.mkdir(parents=True, exist_ok=True)
    engine = create_engine(
        url,
        connect_args={"check_same_thread": False} if url.startswith("sqlite") else {},
        pool_pre_ping=True,
    )
    if url.startswith("sqlite"):

        @event.listens_for(engine, "connect")
        def sqlite_pragmas(connection: Any, _: Any) -> None:
            connection.execute("PRAGMA foreign_keys=ON")
            connection.execute("PRAGMA busy_timeout=5000")

    return engine


def migrate(url: str) -> None:
    from alembic import command
    from alembic.config import Config

    cfg = Config()
    cfg.set_main_option("script_location", str(Path(__file__).parent / "migrations"))
    cfg.set_main_option("sqlalchemy.url", url.replace("%", "%%"))
    make_engine(url).dispose()
    command.upgrade(cfg, "head")


def sessions(engine: Engine) -> Iterator[Session]:
    with sessionmaker(engine, expire_on_commit=False)() as session:
        yield session
