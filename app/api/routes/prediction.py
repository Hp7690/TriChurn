"""POST /predict: Churn probability, label and risk band (Phase 2)."""
from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Depends

from app.api.dependencies import get_services
from app.schemas.common import CustomerRequest, ErrorResponse
from app.schemas.prediction import PredictionResponse
from app.services.container import Services

router = APIRouter(tags=["prediction"])
ERRORS = {422: {"model": ErrorResponse}, 500: {"model": ErrorResponse}, 503: {"model": ErrorResponse}}


@router.post(
    "/predict", response_model=PredictionResponse, responses=ERRORS,
    summary="Churn probability, label and risk band (Phase 2)",
)
def predict(
    request: CustomerRequest,
    services: Annotated[Services, Depends(get_services)],
) -> PredictionResponse:
    return services.prediction.predict(request)
