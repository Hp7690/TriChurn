"""POST /business: CLV, value at risk, ENB, decision and best action (Phase 4)."""
from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Depends

from app.api.dependencies import get_services
from app.schemas.business import BusinessResponse
from app.schemas.common import CustomerRequest, ErrorResponse
from app.services.container import Services

router = APIRouter(tags=["business"])
ERRORS = {422: {"model": ErrorResponse}, 500: {"model": ErrorResponse}, 503: {"model": ErrorResponse}}


@router.post(
    "/business", response_model=BusinessResponse, responses=ERRORS,
    summary="CLV, value at risk, ENB, decision and best action (Phase 4)",
)
def business(
    request: CustomerRequest,
    services: Annotated[Services, Depends(get_services)],
) -> BusinessResponse:
    return services.business.business(request)
