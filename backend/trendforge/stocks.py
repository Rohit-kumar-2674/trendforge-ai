from typing import Any

import numpy as np
import pandas as pd


def technicals(
    values: list[float],
    volumes: list[float] | None = None,
    highs: list[float] | None = None,
    lows: list[float] | None = None,
) -> dict[str, Any]:
    s = pd.Series(values, dtype=float)
    if len(s) < 30:
        return {"status": "INSUFFICIENT DATA"}
    changes = s.diff()
    gains = changes.clip(lower=0).ewm(alpha=1 / 14, adjust=False).mean().iloc[-1]
    losses = (-changes.clip(upper=0)).ewm(alpha=1 / 14, adjust=False).mean().iloc[-1]
    rsi = 50 if gains == losses == 0 else 100 if losses == 0 else 100 - 100 / (1 + gains / losses)
    ema12, ema26 = s.ewm(span=12, adjust=False).mean(), s.ewm(span=26, adjust=False).mean()
    macd = ema12 - ema26
    sma20 = float(s.tail(20).mean())
    sma50 = float(s.tail(50).mean())
    volatility = float(np.log(s.clip(lower=1e-8)).diff().tail(20).std())
    regime = (
        "High Volatility"
        if volatility > 0.03
        else "Bull Trend"
        if s.iloc[-1] > sma20 > sma50
        else "Bear Trend"
        if s.iloc[-1] < sma20 < sma50
        else "Sideways"
    )
    result: dict[str, Any] = {
        "rsi_14": round(float(rsi), 2),
        "sma_20": round(sma20, 4),
        "sma_50": round(sma50, 4),
        "ema_12": round(float(ema12.iloc[-1]), 4),
        "macd": round(float(macd.iloc[-1]), 4),
        "macd_signal": round(float(macd.ewm(span=9, adjust=False).mean().iloc[-1]), 4),
        "bollinger_upper": round(sma20 + 2 * float(s.tail(20).std()), 4),
        "bollinger_lower": round(sma20 - 2 * float(s.tail(20).std()), 4),
        "daily_volatility": volatility,
        "drawdown": round(float(s.iloc[-1] / s.max() - 1), 5),
        "regime": regime,
        "regime_scope": "This asset only; a broad-market regime requires a configured benchmark",
        "relative_volume": None,
        "atr_14": None,
    }
    if volumes and len(volumes) >= 20:
        result["relative_volume"] = round(volumes[-1] / max(float(np.mean(volumes[-20:])), 1), 3)
    if highs and lows and len(highs) == len(lows) == len(values):
        high, low = pd.Series(highs), pd.Series(lows)
        tr = pd.concat([high - low, (high - s.shift()).abs(), (low - s.shift()).abs()], axis=1).max(
            axis=1
        )
        result["atr_14"] = round(float(tr.ewm(alpha=1 / 14, adjust=False).mean().iloc[-1]), 4)
    return result
