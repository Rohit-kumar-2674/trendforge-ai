from datetime import datetime
from typing import Any

import numpy as np


def freshness(
    source: datetime | None, retrieved: datetime | None, now: datetime, interval_hours: float = 24
) -> dict[str, Any]:
    if not source or not retrieved:
        return {
            "status": "UNAVAILABLE",
            "source_timestamp": None,
            "retrieved_at": None,
            "age_hours": None,
            "expected_interval_hours": interval_hours,
        }
    age = max(0.0, (now - source).total_seconds() / 3600)
    status = (
        "FRESH"
        if age <= interval_hours * 1.5
        else "DELAYED"
        if age <= interval_hours * 3
        else "STALE"
    )
    return {
        "status": status,
        "source_timestamp": source.isoformat(),
        "retrieved_at": retrieved.isoformat(),
        "age_hours": round(age, 1),
        "expected_interval_hours": interval_hours,
        "timezone": "UTC",
        "realtime": False,
    }


def quality(values: list[float], dates: list[datetime], cadence: str) -> dict[str, Any]:
    arr = np.asarray(values, dtype=float)
    flags: list[str] = []
    if len(arr) < 30:
        flags.append("Less than 30 observations")
    finite = bool(np.isfinite(arr).all() and (arr >= 0).all())
    if not finite:
        flags.append("Invalid numeric values")
    duplicates = len(dates) - len(set(dates))
    if duplicates:
        flags.append("Duplicate timestamps")
    gaps = 0
    for a, b in zip(dates, dates[1:], strict=False):
        if cadence == "trading_session":
            missing = int(np.busday_count(a.date(), b.date())) - 1
        else:
            missing = (b.date() - a.date()).days - 1
        gaps += max(0, missing)
    if gaps:
        flags.append(f"{gaps} missing expected days (exchange holidays may explain financial gaps)")
    jumps = 0
    if len(arr) > 1:
        returns = np.diff(np.log(np.maximum(arr, 1e-8)))
        jumps = int((np.abs(returns) > np.log(2)).sum())
        if jumps:
            flags.append(
                f"{jumps} extreme changes; check events, unit changes and corporate actions"
            )
    completeness = len(arr) / max(1, len(arr) + gaps)
    score = 100 * completeness - min(30, jumps * 5) - duplicates * 5 - (0 if finite else 80)
    return {
        "score": round(max(0, score), 1),
        "completeness": round(completeness, 3),
        "missing_days": gaps,
        "outliers": jumps,
        "sample_size": len(arr),
        "flags": flags,
    }
