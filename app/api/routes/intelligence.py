"""POST /customer-intelligence: Prediction, explanation, business decision and segment."""
from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Depends

from app.api.dependencies import get_services
from app.schemas.common import CustomerRequest, ErrorResponse
from app.schemas.intelligence import CustomerIntelligenceResponse
from app.services.container import Services

router = APIRouter(tags=["intelligence"])
ERRORS = {422: {"model": ErrorResponse}, 500: {"model": ErrorResponse}, 503: {"model": ErrorResponse}}


@router.post(
    "/customer-intelligence", response_model=CustomerIntelligenceResponse, responses=ERRORS,
    summary="Prediction, explanation, business decision and segment",
)
def customer_intelligence(
    request: CustomerRequest,
    services: Annotated[Services, Depends(get_services)],
) -> CustomerIntelligenceResponse:
    return services.intelligence.analyze(request)
