from datetime import UTC, datetime, timedelta

import numpy as np
import pytest
from sqlalchemy.orm import Session

from trendforge.config import Settings
from trendforge.db import make_engine, migrate
from trendforge.providers.base import ProviderBatch
from trendforge.schemas import Domain, EntityInput, ObservationInput, utcnow


@pytest.fixture
def settings(tmp_path):
    return Settings(
        database_url=f"sqlite:///{tmp_path}/test.db",
        demo_mode=True,
        reports_dir=tmp_path / "reports",
        _env_file=None,
    )


@pytest.fixture
def session(settings):
    migrate(settings.database_url)
    engine = make_engine(settings.database_url)
    with Session(engine, expire_on_commit=False) as session:
        yield session
    engine.dispose()


@pytest.fixture
def values():
    rng = np.random.default_rng(2674)
    return (100 * np.exp(np.cumsum(rng.normal(0.001, 0.02, 560)))).tolist()


@pytest.fixture
def dates():
    return [datetime(2024, 1, 1, tzinfo=UTC) + timedelta(days=i) for i in range(560)]


@pytest.fixture
def batch(values):
    now = utcnow()
    end = now.replace(hour=23, minute=59, second=0, microsecond=0) - timedelta(days=1)
    entity = EntityInput(
        id="demo:test",
        name="Synthetic Test",
        domain=Domain.TECHNOLOGY,
        primary_metric="interest",
        synthetic=True,
    )
    rows = [
        ObservationInput(
            entity_id=entity.id,
            provider="demo",
            metric="interest",
            value=value,
            source_timestamp=end - timedelta(days=len(values) - 1 - i),
            retrieved_at=now,
            synthetic=True,
            unit="index",
        )
        for i, value in enumerate(values)
    ]
    return ProviderBatch(entities=[entity], observations=rows)
