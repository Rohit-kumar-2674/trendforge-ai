from collections.abc import Iterator
from typing import Any

import numpy as np
from sklearn.metrics import (
    accuracy_score,
    balanced_accuracy_score,
    f1_score,
    log_loss,
    matthews_corrcoef,
    precision_score,
    recall_score,
)

from trendforge.forecasting.baseline import CLASSES, forecast
from trendforge.trends.analogues import outcome_class


def purged_splits(
    n: int, *, horizon: int, min_train: int = 80, test_size: int = 30, rolling: int | None = None
) -> Iterator[tuple[np.ndarray, np.ndarray]]:
    """Training labels must END strictly before the first validation feature timestamp."""
    if min(horizon, min_train, test_size) < 1:
        raise ValueError("Split sizes must be positive")
    for start in range(min_train + horizon, n - horizon, test_size):
        train_end = start - horizon
        train_start = max(0, train_end - rolling) if rolling else 0
        train = np.arange(train_start, train_end)
        test = np.arange(start, min(start + test_size, n - horizon))
        if len(train) and len(test):
            if int(train[-1]) + horizon >= int(test[0]):
                raise AssertionError("Label leakage across split boundary")
            yield train, test


def reliability(
    y: list[str], probabilities: list[dict[str, float]], bins: int = 10
) -> dict[str, list[dict[str, Any]]]:
    result: dict[str, list[dict[str, Any]]] = {}
    for c in CLASSES:
        points = []
        for b in range(bins):
            low, high = b / bins, (b + 1) / bins
            selected = [
                i
                for i, p in enumerate(probabilities)
                if low <= p[c] < high or (b == bins - 1 and p[c] == 1)
            ]
            if selected:
                points.append(
                    {
                        "predicted_probability": float(
                            np.mean([probabilities[i][c] for i in selected])
                        ),
                        "actual_frequency": float(np.mean([y[i] == c for i in selected])),
                        "sample_size": len(selected),
                        "bin_start": low,
                        "bin_end": high,
                    }
                )
        result[c] = points
    return result


def metrics(y: list[str], probabilities: list[dict[str, float]]) -> dict[str, Any]:
    if not y:
        return {"sample_size": 0, "status": "NO MATURED FORECASTS"}
    pred = [max(p, key=lambda c: p[c]) for p in probabilities]
    matrix = np.asarray([[p[c] for c in CLASSES] for p in probabilities])
    actual = np.asarray([[int(label == c) for c in CLASSES] for label in y])
    indexes = [CLASSES.index(label) for label in y]
    return {
        "sample_size": len(y),
        "accuracy": float(accuracy_score(y, pred)),
        "balanced_accuracy": float(balanced_accuracy_score(y, pred)),
        "precision_macro": float(
            precision_score(y, pred, labels=CLASSES, average="macro", zero_division=0)
        ),
        "recall_macro": float(
            recall_score(y, pred, labels=CLASSES, average="macro", zero_division=0)
        ),
        "f1_macro": float(f1_score(y, pred, labels=CLASSES, average="macro", zero_division=0)),
        "mcc": float(matthews_corrcoef(y, pred)),
        "brier_score": float(np.mean(np.sum((matrix - actual) ** 2, axis=1))),
        "brier_definition": "Multiclass sum of squared errors, range 0–2; uniform baseline = 2/3",
        "log_loss": float(log_loss(indexes, matrix, labels=[0, 1, 2])),
        "reliability": reliability(y, probabilities),
    }


def walk_forward(
    values: list[float],
    horizon: int = 7,
    min_history: int = 120,
    method: str = "euclidean",
    window: int = 21,
) -> dict[str, Any]:
    predictions: list[dict[str, float]] = []
    actual: list[str] = []
    records = []
    # Test targets do not overlap: one origin every horizon observations.
    for origin in range(min_history - 1, len(values) - horizon, horizon):
        prediction = forecast(values[: origin + 1], horizon, method=method, window=window)
        if prediction.get("probabilities") is None:
            continue
        change = values[origin + horizon] / max(values[origin], 1e-8) - 1
        label = outcome_class(change, prediction["threshold"])
        predictions.append(prediction["probabilities"])
        actual.append(label)
        records.append(
            {
                "origin_index": origin,
                "target_index": origin + horizon,
                "prediction": prediction["probabilities"],
                "actual_class": label,
                "actual_return": change,
                "confidence": prediction["confidence"],
            }
        )
    return {
        "metrics": metrics(actual, predictions),
        "horizon": horizon,
        "validation": "Expanding walk-forward; purged analogue outcomes; non-overlapping test labels",
        "records": records,
        "limitations": [
            "Retrospective replay is not the immutable prospective forecast ledger",
            "Historical provider data may be revised and is not a point-in-time archive",
            "No strategy or investment performance is claimed",
        ],
    }
