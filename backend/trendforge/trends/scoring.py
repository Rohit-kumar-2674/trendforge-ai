from datetime import datetime
from pathlib import Path
from typing import Any

import numpy as np
import yaml

from trendforge.trends.lifecycle import classify
from trendforge.trends.quality import quality
from trendforge.trends.velocity import derivatives

ENGINE_VERSION = "trend-score-v1"


def load_weights(path: Path | None = None) -> dict[str, dict[str, float]]:
    path = path or Path(__file__).parents[1] / "config" / "weights.yaml"
    result = yaml.safe_load(path.read_text())
    if not isinstance(result, dict) or "default" not in result:
        raise ValueError("Weights must contain a default domain")
    for weights in result.values():
        if (
            not weights
            or any(
                not isinstance(v, (float, int)) or not np.isfinite(v) or v < 0
                for v in weights.values()
            )
            or sum(weights.values()) <= 0
        ):
            raise ValueError("Weights must be finite, nonnegative and have positive total")
    return result


def growth(values: list[float] | np.ndarray, periods: int = 7) -> float:
    if len(values) <= periods or values[-periods - 1] <= 0:
        return 0.0
    return float(values[-1] / values[-periods - 1] - 1)


def percentile_score(value: float, scale: float) -> float:
    return float(np.clip(50 + 50 * np.tanh(value / max(scale, 1e-8)), 0, 100))


def analyze(
    values: list[float],
    dates: list[datetime],
    domain: str,
    cadence: str,
    *,
    sources: int = 1,
    secondary: dict[str, list[float]] | None = None,
    weights: dict[str, float] | None = None,
) -> dict[str, Any]:
    if len(values) < 4:
        raise ValueError("At least four observations are required")
    y = np.asarray(values, dtype=float)
    if not np.isfinite(y).all() or (y < 0).any():
        raise ValueError("Invalid series")
    deltas = np.diff(np.log(np.maximum(y, 1e-8)))
    elapsed = [(x - dates[0]).total_seconds() / 86400 for x in dates]
    kinematics = derivatives(values, elapsed)
    recent_growth = growth(y)
    prev_growth = growth(y[:-7]) if len(y) >= 15 else 0
    relative_acceleration = recent_growth - prev_growth
    baseline = float(np.median(y[-90:-7])) if len(y) > 14 else float(y[0])
    past_returns = deltas[-90:-1]
    median = float(np.median(past_returns)) if len(past_returns) else 0
    mad = float(np.median(np.abs(past_returns - median))) if len(past_returns) else 0
    robust_z = float(np.clip((deltas[-1] - median) / max(1.4826 * mad, 0.005), -50, 50))
    volatility = float(np.std(deltas[-30:]))
    scale = max(0.04, volatility * np.sqrt(7) * 2)
    persistence = float(np.mean(deltas[-14:] > 0))
    components: dict[str, float | None] = {
        "momentum": percentile_score(recent_growth, scale),
        "acceleration": percentile_score(relative_acceleration, scale),
        "persistence": persistence * 100,
        "novelty": float(np.clip((y[-1] / max(float(y.max()), 1e-8) - 0.5) * 200, 0, 100)),
        "anomaly": float(min(100, abs(robust_z) / 6 * 100)),
        "source_diversity": min(100.0, max(0, sources - 1) * 25.0),
        "volume": None,
        "search": None,
        "engagement": None,
        "breadth": None,
        "sentiment": None,
        "geographic_spread": None,
    }
    for metric, series in (secondary or {}).items():
        if metric in ("search", "engagement", "volume") and len(series) > 7:
            components[metric] = percentile_score(growth(series), 0.2)
    configured = weights or load_weights().get(domain, load_weights()["default"])
    available = {k: v for k, v in configured.items() if components.get(k) is not None}
    score = sum(float(components[k] or 0) * w for k, w in available.items()) / max(
        sum(available.values()), 1e-9
    )
    saturation = (
        "High"
        if relative_acceleration < -0.02 and y[-1] > y.max() * 0.85
        else "Moderate"
        if y[-1] > baseline * 1.5
        else "Low"
    )
    novelty = float(components["novelty"] or 0)
    early = float(
        np.clip(
            0.4 * float(components["acceleration"] or 0)
            + 0.3 * persistence * 100
            + 0.2 * novelty
            + 0.1 * float(components["source_diversity"] or 0)
            - (15 if saturation == "High" else 0),
            0,
            100,
        )
    )
    return {
        "current_score": round(score, 1),
        "components": {k: round(v, 1) if v is not None else None for k, v in components.items()},
        "effective_weights": {
            k: round(w / sum(available.values()), 4) for k, w in available.items()
        },
        "weight_coverage": round(sum(available.values()) / sum(configured.values()), 3),
        "growth_7_periods": round(recent_growth * 100, 2),
        "growth_30_periods": round(growth(y, 30) * 100, 2),
        "relative_acceleration": round(relative_acceleration * 100, 3),
        **{k: round(v, 5) for k, v in kinematics.items()},
        "velocity_unit": "primary units / elapsed calendar day",
        "volatility": round(volatility, 6),
        "anomaly_z": round(robust_z, 2),
        "anomaly_detected": abs(robust_z) >= 3.5,
        "lifecycle_stage": classify(
            growth=recent_growth,
            acceleration=relative_acceleration,
            persistence=persistence,
            current=float(y[-1]),
            baseline=baseline,
            historic_peak=float(y.max()),
            n=len(y),
        ),
        "early_signal_score": round(early, 1),
        "breakout_score": round(early, 1),
        "saturation": saturation,
        "source_count": sources,
        "quality": quality(values, dates, cadence),
        "engine_version": ENGINE_VERSION,
        "interpretation": "Heuristic strength index, not a probability; novelty is a numerical high-water-mark proxy, not semantic novelty.",
    }
