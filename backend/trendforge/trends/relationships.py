from typing import Any

import numpy as np
import pandas as pd


def lead_lag(left: pd.Series, right: pd.Series, max_lag: int = 14) -> dict[str, Any]:
    # Compare log CHANGES, not nonstationary levels. Align on actual UTC calendar dates.
    aligned = pd.concat([left.rename("left"), right.rename("right")], axis=1).sort_index()
    aligned = aligned.asfreq("D")
    changes = np.log(aligned.clip(lower=1e-8)).diff()
    results = []
    for lag in range(-max_lag, max_lag + 1):
        pairs = pd.concat([changes["left"], changes["right"].shift(-lag)], axis=1).dropna()
        if len(pairs) >= 30 and (pairs.std() > 1e-9).all():
            correlation = float(pairs.iloc[:, 0].corr(pairs.iloc[:, 1]))
            results.append({"lag_days": lag, "correlation": correlation, "sample_size": len(pairs)})
    if not results:
        return {
            "status": "INSUFFICIENT DATA",
            "samples": [],
            "caution": "At least 30 aligned changes are required",
        }
    best = max(results, key=lambda r: abs(float(r["correlation"])))
    n = int(best["sample_size"])
    z = np.arctanh(np.clip(best["correlation"], -0.99999, 0.99999))
    ci = np.tanh([z - 1.96 / np.sqrt(n - 3), z + 1.96 / np.sqrt(n - 3)])
    return {
        "status": "EXPERIMENTAL",
        "best_lag_days": best["lag_days"],
        "correlation": round(best["correlation"], 4),
        "sample_size": n,
        "naive_95_percent_interval": [round(float(x), 4) for x in ci],
        "samples": results,
        "label": "Possible Lead-Lag Relationship",
        "caution": "Correlation does not establish causation. Positive lag means the left series leads. Interval assumes independent samples and does not correct for autocorrelation or searching many lags; this is exploratory, not a significance claim.",
    }


def seasonality(
    values: list[float], periods: tuple[int, ...] = (7, 30, 90, 365)
) -> list[dict[str, Any]]:
    y = pd.Series(values, dtype=float)
    residual = y - y.rolling(30, min_periods=1).mean()
    output = []
    for period in periods:
        if len(y) >= period * 3 and residual.std() > 1e-9:
            score = residual.autocorr(period)
            if np.isfinite(score):
                output.append(
                    {
                        "period_observations": period,
                        "autocorrelation": round(float(score), 3),
                        "cycles": len(y) // period,
                        "status": "Exploratory recurrence, not seasonally adjusted growth",
                    }
                )
    return output
