"""Phase 3 - result schemas for SHAP explanations.

All SHAP values are in LOG-ODDS (raw margin) space of the locked Logistic Regression, at SOURCE-FEATURE level
(encoded columns are summed back to the feature they came from; see ``feature_importance``).

Wording rule: these numbers describe how a feature moved the MODEL's score relative to the background average.
They are not causal claims about why a customer churns.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

INCREASES_CHURN = "increases_churn"
DECREASES_CHURN = "decreases_churn"
NEUTRAL = "neutral"
DIRECTIONS = (INCREASES_CHURN, DECREASES_CHURN, NEUTRAL)

OUTPUT_SPACE = "log_odds"

INTERPRETATION_NOTE = (
    "SHAP values describe each feature's contribution to the model's churn score (log-odds) relative to the "
    "average of the TRAIN background. A positive value contributed toward a higher model score, a negative value "
    "toward a lower one. They describe the model, not causes: they do not show that a feature caused churn."
)


@dataclass(frozen=True)
class FeatureContribution:
    """One source feature's signed contribution to one customer's score."""
    source_feature: str
    raw_value: Any                # value as seen by the model after type coercion; None when missing (imputed)
    shap_value: float             # log-odds contribution, summed over the feature's encoded columns
    direction: str                # increases_churn | decreases_churn | neutral
    is_engineered: bool = False   # created by the feature-engineering step rather than supplied by the caller

    def to_dict(self) -> dict:
        return {"source_feature": self.source_feature, "raw_value": self.raw_value,
                "shap_value": self.shap_value, "direction": self.direction,
                "is_engineered": self.is_engineered}


@dataclass(frozen=True)
class LocalExplanation:
    prediction_probability: float
    predicted_class: int           # 1 = churn at `threshold` (probability >= threshold)
    threshold: float
    base_value: float              # expected model log-odds over the TRAIN background
    output_space: str              # always "log_odds"
    features: list[FeatureContribution]   # sorted by |shap_value| desc, then name
    model_log_odds: float          # the model's own log-odds; base_value + sum(shap_value) reconstructs it
    reconstruction_error: float    # |base_value + sum(shap_value) - model_log_odds|
    interpretation: str = field(default=INTERPRETATION_NOTE)

    def to_dict(self) -> dict:
        return {"prediction_probability": self.prediction_probability, "predicted_class": self.predicted_class,
                "threshold": self.threshold, "base_value": self.base_value, "output_space": self.output_space,
                "model_log_odds": self.model_log_odds, "reconstruction_error": self.reconstruction_error,
                "features": [f.to_dict() for f in self.features], "interpretation": self.interpretation}


@dataclass(frozen=True)
class GlobalImportanceItem:
    source_feature: str
    mean_abs_shap: float           # mean over rows of |source-level SHAP| (log-odds)
    rank: int                      # 1 = most important; ties broken by feature name

    def to_dict(self) -> dict:
        return {"source_feature": self.source_feature, "mean_abs_shap": self.mean_abs_shap, "rank": self.rank}
