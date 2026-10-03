from typing import Literal

import numpy as np
import pandas as pd


def smooth(
    values: list[float], method: Literal["ema", "sma", "median", "savgol"] = "ema", window: int = 7
) -> np.ndarray:
    """All methods use only the current and earlier samples, including polynomial smoothing."""
    s = pd.Series(values, dtype=float)
    if method == "ema":
        return s.ewm(span=window, adjust=False).mean().to_numpy()
    if method == "sma":
        return s.rolling(window, min_periods=1).mean().to_numpy()
    if method == "median":
        return s.rolling(window, min_periods=1).median().to_numpy()
    if method == "savgol":
        # Trailing polynomial endpoint fit: unlike a centered Savitzky-Golay filter,
        # no future sample can influence a historical value.
        result = []
        for i in range(len(s)):
            segment = s.iloc[max(0, i - window + 1) : i + 1].to_numpy()
            x = np.arange(len(segment))
            result.append(
                float(np.polyval(np.polyfit(x, segment, min(2, len(segment) - 1)), x[-1]))
                if len(segment) > 1
                else float(segment[0])
            )
        return np.asarray(result)
    raise ValueError("Unknown causal smoother")


def derivatives(values: list[float], elapsed_days: list[float] | None = None) -> dict[str, float]:
    if len(values) < 4:
        return {"velocity": 0.0, "acceleration": 0.0, "jerk": 0.0}
    y = smooth(values)
    dt = np.diff(np.asarray(elapsed_days)) if elapsed_days is not None else np.ones(len(y) - 1)
    if np.any(dt <= 0):
        raise ValueError("Timestamps must strictly increase")
    velocity = np.diff(y) / dt
    acceleration = np.diff(velocity) / dt[1:]
    jerk = np.diff(acceleration) / dt[2:]
    return {
        "velocity": float(velocity[-1]),
        "acceleration": float(acceleration[-1]),
        "jerk": float(jerk[-1]),
    }
