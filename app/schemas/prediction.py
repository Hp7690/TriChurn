"""Churn prediction response (Phase 2 model; risk band from the Phase 4 risk-band configuration)."""
from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, Field


class PredictionResponse(BaseModel):
    customer_id: str | None
    churn_probability: float = Field(ge=0.0, le=1.0, description="P(churn) from the locked Phase 2 model.")
    predicted_churn: bool = Field(description="True when churn_probability >= decision_threshold.")
    predicted_label: Literal["CHURN", "NO_CHURN"]
    decision_threshold: float = Field(ge=0.0, le=1.0, description="The threshold stored with the Phase 2 model.")
    risk_band: str = Field(description="Band from the configured Phase 4 risk bands.")
    model_name: str
    model_version: str
