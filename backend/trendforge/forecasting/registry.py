from typing import Any

from sqlalchemy.orm import Session

from trendforge.db import ModelVersion
from trendforge.forecasting.baseline import MODEL_VERSION


def ensure_baseline(session: Session) -> None:
    if session.get(ModelVersion, MODEL_VERSION) is None:
        session.add(
            ModelVersion(
                id=MODEL_VERSION,
                status="PRODUCTION",
                card={
                    "name": "Historical analogue frequency with symmetric Dirichlet prior",
                    "release": "0.1.0",
                    "role": "Enabled experimental baseline, not a validated investment model",
                    "training": "Per-entity expanding history available when forecast is issued",
                    "features": ["Normalized trailing log pattern"],
                    "window": 21,
                    "validation": "Purged walk-forward available separately; prospective ledger starts empty",
                    "calibration": "Unvalidated; no calibrated-probability claim",
                    "class_prior": [1, 1, 1],
                    "confidence_cap": "LOW",
                    "analogue_selection": "Disjoint pattern+outcome intervals before query start",
                    "limitations": [
                        "Demo series are synthetic",
                        "Provider histories may be revised",
                        "No representative universe or survivorship-free guarantee",
                        "Small analogue samples",
                    ],
                },
            )
        )


def promotion_decision(candidate: dict[str, Any], production: dict[str, Any]) -> dict[str, Any]:
    reasons = []
    if candidate.get("synthetic", True):
        reasons.append("Synthetic or unspecified data cannot qualify")
    if candidate.get("sample_size", 0) < 200:
        reasons.append("Fewer than 200 matured prospective holdout forecasts")
    if candidate.get("evaluation_id") != production.get("evaluation_id") or not candidate.get(
        "evaluation_id"
    ):
        reasons.append("Models were not compared on the same locked holdout")
    if not candidate.get("prospective", False):
        reasons.append("Retrospective model selection is not a prospective holdout")
    if candidate.get("brier_score", 2) >= production.get("brier_score", 2) - 0.01:
        reasons.append("Brier improvement is below 0.01")
    if candidate.get("log_loss", 100) > production.get("log_loss", 100):
        reasons.append("Log loss regressed")
    if candidate.get("balanced_accuracy", 0) < production.get("balanced_accuracy", 1):
        reasons.append("Balanced accuracy regressed")
    if (
        candidate.get("regime_checks_passed") is not True
        or candidate.get("calibration_checks_passed") is not True
    ):
        reasons.append("Regime or calibration checks not passed")
    return {
        "eligible": not reasons,
        "decision": "ELIGIBLE FOR REVIEW" if not reasons else "REJECTED",
        "reasons": reasons,
        "automatic_promotion": False,
    }
