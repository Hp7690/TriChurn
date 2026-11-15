"""Combined customer-intelligence response: prediction -> explanation -> business decision -> segment."""
from __future__ import annotations

from pydantic import BaseModel

from app.schemas.business import BusinessResponse
from app.schemas.explainability import ExplainResponse
from app.schemas.prediction import PredictionResponse
from app.schemas.segmentation import SegmentResponse


class CustomerIntelligenceResponse(BaseModel):
    customer_id: str | None
    prediction: PredictionResponse
    explanation: ExplainResponse
    business: BusinessResponse
    segment: SegmentResponse
    notes: list[str]
