"""Phase 3 SHAP explanation response. SHAP describes the MODEL's score, not causes of churn."""
from __future__ import annotations

from typing import Literal

from pydantic import BaseModel

Direction = Literal["increases_churn", "decreases_churn", "neutral"]


class FeatureContributionOut(BaseModel):
    source_feature: str
    raw_value: str | int | float | bool | None
    shap_value: float
    direction: Direction
    is_engineered: bool


class ExplainResponse(BaseModel):
    customer_id: str | None
    churn_probability: float
    predicted_churn: bool
    decision_threshold: float
    output_space: str
    base_value: float
    model_log_odds: float
    reconstruction_error: float
    features: list[FeatureContributionOut]
    interpretation: str
    model_version: str
