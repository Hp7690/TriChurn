"""Orchestrates prediction -> explainability -> business -> segmentation. Each step is computed once, by the existing
Phase 2-5 code (through the adapter); the probability and explanation are handed forward, never recomputed."""
from __future__ import annotations

import math

from app.core.errors import inconsistent_results
from app.schemas.common import CustomerRequest
from app.schemas.intelligence import CustomerIntelligenceResponse
from app.services.adapters.interface import BusinessResult, ExplanationResult, PredictionResult
from app.services.business_service import BusinessService
from app.services.explainability_service import ExplainabilityService
from app.services.mappers import to_business, to_explanation, to_prediction, to_segment
from app.services.prediction_service import PredictionService
from app.services.segmentation_service import SegmentationService

PROBABILITY_TOLERANCE = 1e-6          # same tolerance as the Phase 3 SHAP reconstruction check

NOTES = [
    "Probabilities come from the locked Phase 2 model; SHAP values (Phase 3) describe the model's score, not causes.",
    "Business figures (CLV, value at risk, expected net benefit) are estimates under configured assumptions "
    "(Phase 4); success rates are assumptions, not measured causal effects.",
    "The segment is a nearest-centroid assignment to the locked Phase 5 segmentation; it is descriptive.",
]


def _consistent(p: PredictionResult, e: ExplanationResult, b: BusinessResult) -> bool:
    return (math.isclose(p.churn_probability, e.prediction_probability, abs_tol=PROBABILITY_TOLERANCE)
            and math.isclose(p.churn_probability, b.churn_probability, abs_tol=PROBABILITY_TOLERANCE)
            and math.isclose(p.decision_threshold, e.threshold, abs_tol=PROBABILITY_TOLERANCE)
            and p.predicted_churn == (e.predicted_class == 1) and p.risk_band == b.risk_band)


class IntelligenceService:
    def __init__(self, prediction: PredictionService, explainability: ExplainabilityService,
                 business: BusinessService, segmentation: SegmentationService):
        self._prediction, self._explain = prediction, explainability
        self._business, self._segment = business, segmentation

    def analyze(self, request: CustomerRequest) -> CustomerIntelligenceResponse:
        prediction = self._prediction.run(request)
        explanation = self._explain.run(request)
        business = self._business.run(request, prediction.churn_probability, explanation)
        segment = self._segment.run(request)
        if not _consistent(prediction, explanation, business):
            raise inconsistent_results()
        cid = request.customer_id
        return CustomerIntelligenceResponse(
            customer_id=cid, prediction=to_prediction(cid, prediction), explanation=to_explanation(cid, explanation),
            business=to_business(cid, business), segment=to_segment(cid, segment), notes=list(NOTES))
