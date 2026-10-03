from typing import Any

import numpy as np
import pandas as pd
from sklearn.ensemble import HistGradientBoostingClassifier, RandomForestClassifier
from sklearn.linear_model import LogisticRegression
from sklearn.pipeline import make_pipeline
from sklearn.preprocessing import StandardScaler

from trendforge.forecasting.baseline import CLASSES
from trendforge.forecasting.validation import metrics, purged_splits


def feature_matrix(values: list[float]) -> np.ndarray:
    """Causal features; fit-time scaling happens inside each chronological fold."""
    s = pd.Series(values, dtype=float)
    returns = np.log(s.clip(lower=1e-8)).diff()
    return (
        pd.DataFrame(
            {
                "return_1": returns,
                "return_7": s.pct_change(7),
                "volatility_20": returns.rolling(20).std(),
                "sma_gap": s / s.rolling(20).mean() - 1,
                "acceleration": s.pct_change(7).diff(7),
            }
        )
        .fillna(0)
        .to_numpy()
    )


def compare_models(values: list[float], horizon: int = 7) -> dict[str, Any]:
    if len(values) < 180:
        return {"status": "INSUFFICIENT DATA", "required": 180}
    x = feature_matrix(values)
    s = pd.Series(values)
    # Every target threshold uses ONLY the volatility at that feature timestamp.
    thresholds = np.maximum(
        0.01,
        np.log(s.clip(lower=1e-8)).diff().rolling(60, min_periods=20).std().fillna(0.02).to_numpy()
        * np.sqrt(horizon)
        * 0.5,
    )
    future = s.shift(-horizon) / s - 1
    labels = np.where(future > thresholds, 0, np.where(future < -thresholds, 2, 1))
    factories = {
        "logistic_regression": lambda: make_pipeline(
            StandardScaler(), LogisticRegression(max_iter=1000, C=0.5)
        ),
        "random_forest": lambda: RandomForestClassifier(
            n_estimators=80, max_depth=4, min_samples_leaf=12, random_state=2674, n_jobs=1
        ),
        "gradient_boosting": lambda: HistGradientBoostingClassifier(
            max_iter=60, max_leaf_nodes=7, l2_regularization=2, random_state=2674
        ),
    }
    model_predictions: dict[str, list[dict[str, float]]] = {name: [] for name in factories}
    truth: list[str] = []
    folds = []
    for train, test in purged_splits(len(values), horizon=horizon, min_train=100, test_size=35):
        train = train[train >= 20]
        # Keep one global origin grid across folds, including when the horizon
        # does not divide test_size. Restarting the grid in each fold overlaps targets.
        test = test[(test - (100 + horizon)) % horizon == 0]
        if len(np.unique(labels[train])) < 2 or len(test) == 0:
            continue
        folds.append(
            {
                "train_start": int(train[0]),
                "train_end": int(train[-1]),
                "last_training_label": int(train[-1]) + horizon,
                "validation_start": int(test[0]),
                "validation_end": int(test[-1]),
            }
        )
        truth.extend(CLASSES[int(labels[i])] for i in test)
        for name, factory in factories.items():
            model = factory()
            model.fit(x[train], labels[train])
            raw = model.predict_proba(x[test])
            for row in raw:
                mapped = {c: 0.0 for c in CLASSES}
                for label, probability in zip(model.classes_, row, strict=True):
                    mapped[CLASSES[int(label)]] = float(probability)
                model_predictions[name].append(mapped)
    if not truth:
        return {"status": "INSUFFICIENT CLASS VARIATION"}
    ensemble = [
        {c: float(np.mean([p[i][c] for p in model_predictions.values()])) for c in CLASSES}
        for i in range(len(truth))
    ]
    return {
        "status": "EXPERIMENTAL",
        "horizon": horizon,
        "models": {name: metrics(truth, p) for name, p in model_predictions.items()},
        "ensemble": metrics(truth, ensemble),
        "folds": folds,
        "calibration": "Uncalibrated research outputs; no production promotion",
        "features": ["return_1", "return_7", "volatility_20", "sma_gap", "acceleration"],
        "warning": "Same-series comparison is exploratory and can overfit model choice. A separate prospective holdout and data rights are required before promotion.",
    }
