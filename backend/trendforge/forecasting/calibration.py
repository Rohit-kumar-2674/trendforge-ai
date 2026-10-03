import numpy as np
from sklearn.isotonic import IsotonicRegression
from sklearn.linear_model import LogisticRegression


class ChronologicalCalibrator:
    """One-vs-rest research calibration fitted on a separate, later holdout."""

    def __init__(self, method: str = "platt") -> None:
        if method not in ("platt", "isotonic"):
            raise ValueError("Unknown calibration method")
        self.method = method
        self.models: list[object] = []
        self.fitted = False

    def fit(
        self,
        probabilities: np.ndarray,
        labels: np.ndarray,
        *,
        base_last_label_index: int,
        calibration_first_index: int,
    ) -> "ChronologicalCalibrator":
        if base_last_label_index >= calibration_first_index:
            raise ValueError("Calibration overlaps base-model training labels")
        if len(labels) < 100 or any(int((labels == i).sum()) < 10 for i in range(3)):
            raise ValueError("Calibration requires 100 holdout samples and 10 per class")
        self.models = []
        for c in range(3):
            y = (labels == c).astype(int)
            p = probabilities[:, c]
            if self.method == "isotonic":
                model = IsotonicRegression(out_of_bounds="clip").fit(p, y)
            else:
                logit = np.log(np.clip(p, 1e-6, 1 - 1e-6) / np.clip(1 - p, 1e-6, 1)).reshape(-1, 1)
                model = LogisticRegression().fit(logit, y)
            self.models.append(model)
        self.fitted = True
        return self

    def predict(self, probabilities: np.ndarray) -> np.ndarray:
        if not self.fitted:
            raise ValueError("Calibrator is not fitted")
        columns = []
        for c, model in enumerate(self.models):
            p = probabilities[:, c]
            if isinstance(model, IsotonicRegression):
                columns.append(model.predict(p))
            elif isinstance(model, LogisticRegression):
                logit = np.log(np.clip(p, 1e-6, 1 - 1e-6) / np.clip(1 - p, 1e-6, 1)).reshape(-1, 1)
                columns.append(model.predict_proba(logit)[:, 1])
        result = np.clip(np.column_stack(columns), 1e-8, 1)
        return result / result.sum(axis=1, keepdims=True)
