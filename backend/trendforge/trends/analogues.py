from typing import Any

import numpy as np


def normalized_pattern(values: np.ndarray) -> np.ndarray:
    logs = np.log(np.maximum(values, 1e-8))
    return (logs - logs[0]) / max(float(np.std(np.diff(logs))) * np.sqrt(len(logs)), 0.025)


def distance(a: np.ndarray, b: np.ndarray, method: str) -> float:
    if method == "euclidean":
        return float(np.sqrt(np.mean((a - b) ** 2)))
    if method == "cosine":
        denom = np.linalg.norm(a) * np.linalg.norm(b)
        return float(1 - np.dot(a, b) / denom) if denom > 1e-9 else float(np.linalg.norm(a - b))
    if method == "correlation":
        return (
            float(1 - np.corrcoef(a, b)[0, 1])
            if min(np.std(a), np.std(b)) > 1e-9
            else float(np.linalg.norm(a - b))
        )
    if method == "dtw":
        matrix = np.full((len(a) + 1, len(b) + 1), np.inf)
        matrix[0, 0] = 0
        for i in range(1, len(a) + 1):
            for j in range(max(1, i - 3), min(len(b), i + 3) + 1):
                matrix[i, j] = abs(a[i - 1] - b[j - 1]) + min(
                    matrix[i - 1, j], matrix[i, j - 1], matrix[i - 1, j - 1]
                )
        return float(matrix[-1, -1] / len(a))
    raise ValueError("Unsupported similarity method")


def outcome_class(change: float, threshold: float) -> str:
    return "up" if change > threshold else "down" if change < -threshold else "sideways"


def find_analogues(
    values: list[float],
    horizon: int = 7,
    window: int = 21,
    limit: int = 20,
    method: str = "euclidean",
    threshold: float = 0.02,
) -> list[dict[str, Any]]:
    """Candidates and their outcomes end BEFORE the current query window.

    Selected pattern+outcome intervals are also disjoint from one another.
    This is intentionally conservative about the effective historical sample size.
    """
    if horizon < 1 or window < 3:
        raise ValueError("Invalid horizon or window")
    y = np.asarray(values, dtype=float)
    query_start = len(y) - window
    if query_start < window + horizon:
        return []
    query = normalized_pattern(y[query_start:])
    candidates: list[dict[str, Any]] = []
    for end in range(window - 1, query_start - horizon):
        start = end - window + 1
        pattern = normalized_pattern(y[start : end + 1])
        d = distance(query, pattern, method)
        change = float(y[end + horizon] / max(y[end], 1e-8) - 1)
        candidates.append(
            {
                "start_index": start,
                "end_index": end,
                "outcome_index": end + horizon,
                "distance": round(d, 5),
                "similarity": round(1 / (1 + d), 4),
                "future_return": round(change, 6),
                "outcome": outcome_class(change, threshold),
            }
        )
    selected: list[dict[str, Any]] = []
    for candidate in sorted(candidates, key=lambda x: (x["distance"], x["end_index"])):
        if candidate["similarity"] < 0.35:
            continue
        if any(
            not (
                candidate["outcome_index"] < x["start_index"]
                or candidate["start_index"] > x["outcome_index"]
            )
            for x in selected
        ):
            continue
        selected.append(candidate)
        if len(selected) >= limit:
            break
    return selected
