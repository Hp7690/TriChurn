"""POST /explain: SHAP explanation of the model's score (Phase 3)."""
from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Depends

from app.api.dependencies import get_services
from app.schemas.common import ErrorResponse, ExplainRequest
from app.schemas.explainability import ExplainResponse
from app.services.container import Services

router = APIRouter(tags=["explainability"])
ERRORS = {422: {"model": ErrorResponse}, 500: {"model": ErrorResponse}, 503: {"model": ErrorResponse}}


@router.post(
    "/explain", response_model=ExplainResponse, responses=ERRORS,
    summary="SHAP explanation of the model's score (Phase 3)",
)
def explain(
    request: ExplainRequest,
    services: Annotated[Services, Depends(get_services)],
) -> ExplainResponse:
    return services.explainability.explain(request)
