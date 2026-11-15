"""Service container built once per application from an adapter."""
from __future__ import annotations

from dataclasses import dataclass

from app.services.adapters.interface import Phase15Port
from app.services.business_service import BusinessService
from app.services.explainability_service import ExplainabilityService
from app.services.intelligence_service import IntelligenceService
from app.services.prediction_service import PredictionService
from app.services.segmentation_service import SegmentationService


@dataclass(frozen=True)
class Services:
    adapter: Phase15Port
    prediction: PredictionService
    explainability: ExplainabilityService
    business: BusinessService
    segmentation: SegmentationService
    intelligence: IntelligenceService


def build_services(adapter: Phase15Port) -> Services:
    prediction, explain = PredictionService(adapter), ExplainabilityService(adapter)
    business, segment = BusinessService(adapter), SegmentationService(adapter)
    return Services(adapter, prediction, explain, business, segment,
                    IntelligenceService(prediction, explain, business, segment))
