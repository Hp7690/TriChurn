"""POST /segment: Segment from the locked Phase 5 artifact (no refit)."""
from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Depends

from app.api.dependencies import get_services
from app.schemas.common import CustomerRequest, ErrorResponse
from app.schemas.segmentation import SegmentResponse
from app.services.container import Services

router = APIRouter(tags=["segmentation"])
ERRORS = {422: {"model": ErrorResponse}, 500: {"model": ErrorResponse}, 503: {"model": ErrorResponse}}


@router.post(
    "/segment", response_model=SegmentResponse, responses=ERRORS,
    summary="Segment from the locked Phase 5 artifact (no refit)",
)
def segment(
    request: CustomerRequest,
    services: Annotated[Services, Depends(get_services)],
) -> SegmentResponse:
    return services.segmentation.segment(request)
