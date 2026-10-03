import numpy as np
import pytest

from trendforge.forecasting.baseline import forecast
from trendforge.forecasting.calibration import ChronologicalCalibrator
from trendforge.forecasting.ensemble import compare_models, feature_matrix
from trendforge.forecasting.registry import promotion_decision
from trendforge.forecasting.validation import metrics, purged_splits, walk_forward


def test_probabilities_sum_to_one_and_demo_is_labeled(values):
    result = forecast(values, synthetic=True)
    assert sum(result["probabilities"].values()) == pytest.approx(1)
    assert all(0 < p < 1 for p in result["probabilities"].values())
    assert result["confidence"] in ("LOW", "VERY LOW")
    assert result["status"] == "MOCK/DEMO"
    assert result["calibration"] == "UNVALIDATED"


def test_insufficient_history_returns_no_probability():
    assert forecast([100] * 50)["probabilities"] is None
    assert forecast([100] * 1000)["probabilities"] is not None


def test_regime_shock_reduces_confidence(values):
    result = forecast(values[:-1] + [values[-1] * 30])
    if result.get("probabilities"):
        assert result["out_of_distribution"]
        assert result["confidence"] == "VERY LOW"


@pytest.mark.parametrize("rolling", [None, 100])
@pytest.mark.parametrize("horizon", [1, 5, 20])
def test_purged_splits_never_include_unknown_labels(rolling, horizon):
    folds = list(purged_splits(400, horizon=horizon, rolling=rolling))
    assert folds
    for train, test in folds:
        assert train[-1] + horizon < test[0]
        assert not set(train).intersection(test)
        assert test[-1] + horizon < 400
        if rolling:
            assert len(train) <= rolling


def test_future_append_cannot_change_feature_prefix(values):
    original = feature_matrix(values[:250])
    attacked = feature_matrix(values[:250] + [1e12] * 40)
    assert np.array_equal(original, attacked[:250])


def test_walk_forward_test_outcomes_do_not_overlap(values):
    result = walk_forward(values, horizon=7)
    assert result["metrics"]["sample_size"] > 10
    for a, b in zip(result["records"], result["records"][1:], strict=False):
        assert a["target_index"] <= b["origin_index"]
    for row in result["records"][:3]:
        rebuilt = forecast(values[: row["origin_index"] + 1], 7)
        assert row["prediction"] == rebuilt["probabilities"]


def test_scoring_metrics_have_known_values():
    truth = ["up", "sideways", "down"]
    uniform = [{"up": 1 / 3, "sideways": 1 / 3, "down": 1 / 3}] * 3
    result = metrics(truth, uniform)
    assert result["brier_score"] == pytest.approx(2 / 3)
    assert result["log_loss"] == pytest.approx(np.log(3))
    assert result["reliability"]["up"][0]["sample_size"] == 3


def test_calibration_rejects_training_overlap():
    p = np.ones((120, 3)) / 3
    y = np.tile([0, 1, 2], 40)
    with pytest.raises(ValueError, match="overlaps"):
        ChronologicalCalibrator().fit(p, y, base_last_label_index=120, calibration_first_index=100)


@pytest.mark.parametrize("method", ["platt", "isotonic"])
def test_calibration_uses_separate_holdout(method):
    rng = np.random.default_rng(2)
    p = rng.dirichlet([2, 2, 2], size=150)
    y = np.tile([0, 1, 2], 50)
    calibrated = (
        ChronologicalCalibrator(method)
        .fit(p, y, base_last_label_index=99, calibration_first_index=101)
        .predict(p[:10])
    )
    assert np.allclose(calibrated.sum(axis=1), 1)
    assert np.all(calibrated > 0)


@pytest.mark.parametrize("horizon", [7, 20])
def test_research_ensemble_uses_chronological_folds(values, horizon):
    result = compare_models(values[:240], horizon=horizon)
    assert set(result["models"]) == {"logistic_regression", "random_forest", "gradient_boosting"}
    assert result["ensemble"]["sample_size"] > 0
    assert all(f["last_training_label"] < f["validation_start"] for f in result["folds"])
    for previous, following in zip(result["folds"], result["folds"][1:], strict=False):
        assert previous["validation_end"] + horizon <= following["validation_start"]


def test_model_promotion_rejects_worse_and_synthetic_models():
    production = {
        "evaluation_id": "holdout-1",
        "brier_score": 0.5,
        "log_loss": 0.8,
        "balanced_accuracy": 0.6,
    }
    candidate = {
        "evaluation_id": "holdout-1",
        "sample_size": 500,
        "synthetic": False,
        "prospective": True,
        "regime_checks_passed": True,
        "calibration_checks_passed": True,
        "brier_score": 0.55,
        "log_loss": 0.9,
        "balanced_accuracy": 0.61,
    }
    assert not promotion_decision(candidate, production)["eligible"]
    candidate.update(brier_score=0.45, log_loss=0.7)
    assert promotion_decision(candidate, production)["eligible"]
    candidate["synthetic"] = True
    assert not promotion_decision(candidate, production)["eligible"]
