from datetime import UTC, datetime, timedelta

import numpy as np

from trendforge.providers.base import ProviderBatch, TrendProvider
from trendforge.schemas import Domain, EntityInput, ObservationInput, utcnow

# Fictional names prevent synthetic values being mistaken for a company's real statistics.
CATALOG = [
    ("smart-glasses", "AI smart glasses", Domain.TECHNOLOGY, "Wearables", "GLOBAL", "surge"),
    (
        "local-models",
        "Local language models",
        Domain.TECHNOLOGY,
        "Artificial intelligence",
        "GLOBAL",
        "rise",
    ),
    (
        "vectorflow",
        "VectorFlow / open source",
        Domain.TECHNOLOGY,
        "Developer tools",
        "GLOBAL",
        "surge",
    ),
    ("rust-tools", "Rust developer tools", Domain.TECHNOLOGY, "Programming", "GLOBAL", "steady"),
    ("cherry-red", "Cherry red clothing", Domain.FASHION, "Color", "IN", "rise"),
    ("wide-leg", "Wide-leg denim", Domain.FASHION, "Silhouette", "GLOBAL", "cool"),
    ("retro-runners", "Retro running shoes", Domain.FASHION, "Footwear", "IN", "return"),
    ("ai-filmmaking", "AI filmmaking", Domain.YOUTUBE, "Creator topics", "GLOBAL", "surge"),
    ("slow-living", "Slow living videos", Domain.YOUTUBE, "Creator topics", "GLOBAL", "steady"),
    ("study-streams", "Study with me", Domain.YOUTUBE, "Education", "IN", "seasonal"),
    ("orbital", "ORBT · Orbital Systems", Domain.STOCKS, "Technology", "US", "rise"),
    ("cedar", "CEDR · Cedar Retail", Domain.STOCKS, "Consumer", "US", "cool"),
    ("himalaya", "HIMA · Himalaya Energy", Domain.STOCKS, "Energy", "IN", "volatile"),
    ("solar-search", "Rooftop solar searches", Domain.SEARCH, "Energy", "IN", "rise"),
    ("kdrama", "Hidden-identity K-dramas", Domain.ENTERTAINMENT, "Television", "IN", "return"),
    ("cozy-games", "Cozy exploration games", Domain.ENTERTAINMENT, "Gaming", "GLOBAL", "cool"),
]


class DemoProvider(TrendProvider):
    name = "demo"
    capability = "MOCK/DEMO"
    instructions = "Deterministic synthetic series. Never market or platform data."

    def __init__(self, end: datetime | None = None) -> None:
        super().__init__()
        self.end = end or utcnow().replace(hour=23, minute=59, second=0, microsecond=0) - timedelta(
            days=1
        )

    @property
    def configured(self) -> bool:
        return True

    async def fetch(self) -> ProviderBatch:
        batch = ProviderBatch()
        start = datetime(2025, 1, 1, 23, 59, tzinfo=UTC)
        n = (self.end - start).days + 1
        retrieved = utcnow()
        for idx, (slug, name, domain, category, region, shape) in enumerate(CATALOG):
            stock = domain == Domain.STOCKS
            entity = EntityInput(
                id=f"demo:{slug}",
                name=name,
                domain=domain,
                category=category,
                region=region,
                keywords=[slug.replace("-", " "), category, name],
                primary_metric="close" if stock else "interest",
                unit="USD" if stock and region == "US" else "INR" if stock else "synthetic index",
                cadence="trading_session" if stock else "calendar_day",
                synthetic=True,
            )
            batch.entities.append(entity)
            # RNG seeded per entity and starts on a fixed date: appending never rewrites history.
            rng = np.random.default_rng(2674 + idx)
            shocks = rng.normal(0, 0.012 if stock else 0.027, max(n, 1))
            level = 75.0 + idx * 8
            for day in range(max(0, n)):
                ts = start + timedelta(days=day)
                if stock and ts.weekday() >= 5:
                    continue
                cycle = np.sin(day / (20 + idx % 4) + idx) * 0.006
                phase = (day % 180) / 180
                drift = {
                    "surge": 0.002 + 0.027 * phase**4,
                    "rise": 0.004,
                    "steady": 0.0015,
                    "cool": -0.006 if phase > 0.3 else 0.005,
                    "return": 0.018 if phase > 0.5 else -0.008,
                    "seasonal": 0.022 * np.sin(day * 2 * np.pi / 60),
                    "volatile": 0.001,
                }[shape]
                shock = shocks[day] * (2.8 if shape == "volatile" else 1)
                previous = level
                level = max(0.2, level * np.exp(drift + cycle + shock))
                metrics = {entity.primary_metric: level}
                if stock:
                    metrics.update(
                        open=previous,
                        high=max(previous, level) * 1.009,
                        low=min(previous, level) * 0.992,
                        volume=1_000_000 * (1 + abs(shock) * 18 + 0.1 * np.cos(day)),
                    )
                else:
                    metrics.update(
                        engagement=level * (0.08 + 0.015 * np.sin(day / 9)),
                        search=level * (0.7 + 0.05 * np.cos(day / 11)),
                    )
                for metric, value in metrics.items():
                    batch.observations.append(
                        ObservationInput(
                            entity_id=entity.id,
                            provider=self.name,
                            metric=metric,
                            value=round(float(value), 5),
                            source_timestamp=ts,
                            retrieved_at=retrieved,
                            unit=entity.unit
                            if metric == entity.primary_metric
                            else "synthetic units",
                            synthetic=True,
                            metadata={
                                "generator": "deterministic-v1",
                                "seed": 2674 + idx,
                                "independent_sources": 1,
                            },
                        )
                    )
        return batch
