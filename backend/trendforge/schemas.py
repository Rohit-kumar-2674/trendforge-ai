import math
from datetime import UTC, datetime
from enum import StrEnum
from typing import Any
from urllib.parse import urlparse

from pydantic import BaseModel, Field, field_validator, model_validator


def utcnow() -> datetime:
    return datetime.now(UTC)


class Domain(StrEnum):
    STOCKS = "stocks"
    CRYPTO = "crypto"
    YOUTUBE = "youtube"
    SEARCH = "search"
    FASHION = "fashion"
    TECHNOLOGY = "technology"
    ENTERTAINMENT = "entertainment"
    NEWS = "news"
    GENERAL = "general"


class EntityInput(BaseModel):
    id: str = Field(pattern=r"^[a-zA-Z0-9_.:-]{1,150}$")
    name: str = Field(min_length=1, max_length=200)
    domain: Domain
    category: str = Field(default="", max_length=100)
    region: str = Field(default="GLOBAL", max_length=30)
    keywords: list[str] = Field(default_factory=list, max_length=30)
    primary_metric: str = "interest"
    unit: str = "index"
    cadence: str = "calendar_day"
    synthetic: bool = False
    analytics_allowed: bool = True


class ObservationInput(BaseModel):
    entity_id: str
    provider: str = Field(max_length=80)
    metric: str = Field(pattern=r"^[a-z_]{1,60}$")
    value: float
    source_timestamp: datetime
    retrieved_at: datetime = Field(default_factory=utcnow)
    unit: str = Field(default="count", max_length=40)
    source_url: str | None = None
    synthetic: bool = False
    metadata: dict[str, Any] = Field(default_factory=dict)

    @field_validator("source_timestamp", "retrieved_at")
    @classmethod
    def timezone_required(cls, value: datetime) -> datetime:
        if value.tzinfo is None:
            raise ValueError("An explicit timezone is required")
        return value.astimezone(UTC)

    @field_validator("value")
    @classmethod
    def finite_nonnegative(cls, value: float) -> float:
        if not math.isfinite(value) or value < 0:
            raise ValueError("Observation must be finite and nonnegative")
        return value

    @field_validator("source_url")
    @classmethod
    def safe_url(cls, value: str | None) -> str | None:
        if value:
            url = urlparse(value)
            if url.scheme != "https" or not url.hostname or url.username or url.password:
                raise ValueError("Source links must be credential-free HTTPS URLs")
        return value

    @model_validator(mode="after")
    def chronology(self) -> "ObservationInput":
        if self.source_timestamp > self.retrieved_at:
            raise ValueError("Source timestamp cannot be after retrieval")
        return self


class WatchlistInput(BaseModel):
    entity_id: str = Field(min_length=1, max_length=150)


class ExperimentInput(BaseModel):
    entity_id: str = Field(min_length=1, max_length=150)
    horizon: int = Field(default=7, ge=1, le=30)
    window: int = Field(default=21, ge=7, le=60)
    method: str = Field(default="euclidean", pattern="^(euclidean|cosine|correlation|dtw)$")
