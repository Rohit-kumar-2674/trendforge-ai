from datetime import timedelta

import numpy as np
import pandas as pd
import pytest

from trendforge.stocks import technicals
from trendforge.trends.analogues import distance, find_analogues, normalized_pattern
from trendforge.trends.lifecycle import classify
from trendforge.trends.quality import freshness, quality
from trendforge.trends.relationships import lead_lag, seasonality
from trendforge.trends.scoring import analyze, load_weights
from trendforge.trends.velocity import derivatives, smooth


@pytest.mark.parametrize("method", ["ema", "sma", "median", "savgol"])
def test_smoothing_cannot_see_appended_future(values, method):
    prefix = smooth(values[:180], method)
    hostile_future = values[:180] + [10**9] * 20
    assert np.allclose(prefix, smooth(hostile_future, method)[:180])


def test_derivative_respects_elapsed_time():
    daily = derivatives([10, 20, 30, 40], [0, 1, 2, 3])
    slower = derivatives([10, 20, 30, 40], [0, 2, 4, 6])
    assert slower["velocity"] == pytest.approx(daily["velocity"] / 2)
    with pytest.raises(ValueError):
        derivatives([1, 2, 3, 4], [0, 1, 1, 2])


def test_acceleration_distinguishes_linear_and_explosive(dates):
    linear = [100 + i for i in range(100)]
    explosive = [100 * np.exp(0.0002 * i**2) for i in range(100)]
    a = analyze(linear, dates[:100], "technology", "calendar_day")
    b = analyze(explosive, dates[:100], "technology", "calendar_day")
    assert b["relative_acceleration"] > a["relative_acceleration"]
    assert b["components"]["acceleration"] > a["components"]["acceleration"]


def test_components_missing_are_not_fabricated(values, dates):
    output = analyze(values, dates, "stocks", "calendar_day")
    assert output["components"]["sentiment"] is None
    assert output["components"]["search"] is None
    assert output["source_count"] == 1
    assert output["components"]["source_diversity"] == 0
    assert sum(output["effective_weights"].values()) == pytest.approx(1, abs=0.001)
    assert 0 <= output["current_score"] <= 100


def test_score_prefix_unchanged_by_future(values, dates):
    before = analyze(values[:300], dates[:300], "fashion", "calendar_day")
    after = analyze(
        (values + [1e15])[:300],
        (dates + [dates[-1] + timedelta(days=1)])[:300],
        "fashion",
        "calendar_day",
    )
    assert before == after


def test_invalid_weights_rejected(tmp_path):
    path = tmp_path / "weights.yaml"
    path.write_text("default:\n  momentum: -1\n")
    with pytest.raises(ValueError):
        load_weights(path)


@pytest.mark.parametrize("method", ["euclidean", "cosine", "correlation", "dtw"])
def test_analogue_embargo_and_disjoint_intervals(values, method):
    result = find_analogues(values, horizon=7, method=method)
    assert len(result) >= 3
    for row in result:
        assert row["outcome_index"] < len(values) - 21
        assert row["future_return"] == pytest.approx(
            values[row["end_index"] + 7] / values[row["end_index"]] - 1, abs=1e-6
        )
    intervals = sorted((r["start_index"], r["outcome_index"]) for r in result)
    assert all(a[1] < b[0] for a, b in zip(intervals, intervals[1:], strict=False))


def test_normalization_is_scale_invariant(values):
    a = normalized_pattern(np.asarray(values[:21]))
    b = normalized_pattern(np.asarray(values[:21]) * 1000)
    assert distance(a, b, "euclidean") < 1e-10


def test_short_analogue_history_is_empty():
    assert find_analogues([1, 2, 3, 4]) == []


def test_quality_flags_missing_days_and_spikes(dates):
    q = quality([1, 2, 300, 4], [dates[0], dates[1], dates[5], dates[6]], "calendar_day")
    assert q["missing_days"] == 3
    assert q["outliers"] > 0
    assert q["score"] < 70


def test_weekends_are_not_missing_sessions():
    d = pd.bdate_range("2026-01-01", periods=30, tz="UTC").to_pydatetime().tolist()
    assert quality(list(range(30)), d, "trading_session")["missing_days"] == 0


def test_freshness_uses_source_time_not_successful_fetch(dates):
    now = dates[-1]
    assert freshness(now - timedelta(days=10), now, now)["status"] == "STALE"
    assert freshness(now - timedelta(hours=20), now, now)["status"] == "FRESH"
    assert freshness(now - timedelta(hours=50), now, now)["status"] == "DELAYED"
    assert freshness(None, None, now)["status"] == "UNAVAILABLE"


def test_lead_lag_recovers_known_delayed_signal():
    rng = np.random.default_rng(3)
    returns = rng.normal(0, 0.04, 220)
    first = 100 * np.exp(np.cumsum(returns))
    second = 100 * np.exp(np.cumsum(np.r_[np.zeros(4), returns[:-4]]))
    index = pd.date_range("2025-01-01", periods=220)
    result = lead_lag(pd.Series(first, index), pd.Series(second, index))
    assert result["best_lag_days"] == 4
    assert result["correlation"] > 0.99
    assert "does not establish causation" in result["caution"]


def test_seasonality_requires_multiple_cycles():
    assert seasonality([1, 2, 3]) == []
    seasonal = (100 + np.sin(np.arange(100) * 2 * np.pi / 7) * 10).tolist()
    assert seasonality(seasonal)[0]["autocorrelation"] > 0.85


def test_technicals_handle_flat_and_rising_prices():
    assert technicals([100] * 80)["rsi_14"] == 50
    rising = technicals(list(range(1, 100)))
    assert rising["rsi_14"] == 100
    assert rising["regime"] == "Bull Trend"
    assert rising["sma_20"] == pytest.approx(89.5)


def test_resurgence_is_explicit():
    assert (
        classify(
            growth=0.2,
            acceleration=0.1,
            persistence=0.9,
            current=60,
            baseline=30,
            historic_peak=100,
            n=200,
        )
        == "Resurgent"
    )
