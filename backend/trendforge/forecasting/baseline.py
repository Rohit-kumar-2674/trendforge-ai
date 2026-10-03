from collections import Counter
from typing import Any

import numpy as np

from trendforge.trends.analogues import find_analogues

MODEL_VERSION = "analogue-dirichlet-v1"
CLASSES = ["up", "sideways", "down"]


def wilson(successes: int, n: int) -> list[float] | None:
    if n == 0:
        return None
    p, z = successes / n, 1.96
    center = (p + z * z / (2 * n)) / (1 + z * z / n)
    half = z * np.sqrt(p * (1 - p) / n + z * z / (4 * n * n)) / (1 + z * z / n)
    return [round(float(max(0, center - half)), 4), round(float(min(1, center + half)), 4)]


def forecast(
    values: list[float],
    horizon: int = 7,
    *,
    synthetic: bool = False,
    quality_score: float = 100,
    method: str = "euclidean",
    window: int = 21,
) -> dict[str, Any]:
    if horizon < 1 or horizon > 90:
        raise ValueError("Horizon must be between 1 and 90 observations")
    if len(values) < max(90, 2 * window + horizon + 1):
        return {
            "status": "INSUFFICIENT DATA",
            "horizon": horizon,
            "required_samples": max(90, 2 * window + horizon + 1),
            "available_samples": len(values),
            "probabilities": None,
            "confidence": "VERY LOW",
            "model_version": MODEL_VERSION,
        }
    y = np.asarray(values, dtype=float)
    returns = np.diff(np.log(np.maximum(y, 1e-8)))
    volatility = float(np.std(returns[-60:]))
    threshold = max(0.01, volatility * np.sqrt(horizon) * 0.5)
    analogues = find_analogues(
        values, horizon=horizon, method=method, window=window, threshold=threshold
    )
    if len(analogues) < 3:
        return {
            "status": "INSUFFICIENT ANALOGUES",
            "horizon": horizon,
            "probabilities": None,
            "analogue_count": len(analogues),
            "confidence": "VERY LOW",
            "model_version": MODEL_VERSION,
        }
    counts = Counter(a["outcome"] for a in analogues)
    n = len(analogues)
    probabilities = {c: (counts[c] + 1) / (n + 3) for c in CLASSES}
    direction = max(probabilities, key=lambda c: probabilities[c])
    train_returns = returns[:-21]
    history_std = max(float(np.std(train_returns)), 0.003)
    shift = abs(float(np.mean(returns[-7:])) - float(np.mean(train_returns))) / history_std
    ood = bool(
        shift > 3
        or volatility > history_std * 2.5
        or abs(returns[-1] - np.median(train_returns)) > history_std * 6
    )
    similarity = float(np.mean([a["similarity"] for a in analogues]))
    # No production calibration history yet: this version can never show high confidence.
    confidence = (
        "LOW" if n >= 8 and similarity >= 0.55 and quality_score >= 85 and not ood else "VERY LOW"
    )
    reasons = [
        f"{n} non-overlapping historical analogues",
        "Laplace smoothing adds one observation to each outcome class",
        "No verified live calibration history; confidence is capped at LOW",
    ]
    if synthetic:
        reasons.append(
            "Synthetic demo data: these probabilities have no real-world predictive validity"
        )
    if ood:
        reasons.append(
            "Current conditions differ substantially from the model's historical training distribution"
        )
    if quality_score < 85:
        reasons.append("Incomplete or irregular data reduces confidence")
    intervals = {c: wilson(counts[c], n) for c in CLASSES}
    return {
        "status": "EXPERIMENTAL" if not synthetic else "MOCK/DEMO",
        "model_version": MODEL_VERSION,
        "horizon": horizon,
        "probabilities": probabilities,
        "direction": direction,
        "confidence": confidence,
        "confidence_reasons": reasons,
        "threshold": threshold,
        "class_definition": f"Up above +{threshold:.2%}; down below -{threshold:.2%}; otherwise sideways. Mutually exclusive outcomes.",
        "analogue_count": n,
        "analogue_similarity": round(similarity, 4),
        "historical_counts": {c: counts[c] for c in CLASSES},
        "historical_rate_intervals": intervals,
        "interval_note": "95% Wilson intervals for historical analogue frequencies, not guaranteed future probabilities; dependence and selection bias can remain.",
        "out_of_distribution": ood,
        "calibration": "UNVALIDATED",
        "model_agreement": None,
        "model_votes": [
            {
                "name": "Historical analogue frequency + symmetric prior",
                "probabilities": probabilities,
            }
        ],
        "analogues": analogues,
        "synthetic": synthetic,
        "limitations": [
            "Historical similarity does not establish future reliability",
            "No causal interpretation",
            "Selected historical series may have survivorship and revision bias",
            "No trading execution or return guarantee",
        ],
    }
