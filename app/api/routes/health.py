from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Depends
from fastapi.responses import JSONResponse

from app import __version__
from app.api.dependencies import get_services, get_settings
from app.core.config import API_VERSION, SERVICE_NAME, Settings
from app.schemas.common import HealthResponse, LivenessResponse, ReadinessCheck, ReadinessResponse
from app.services.container import Services

router = APIRouter(tags=["health"])


@router.get("/health", response_model=HealthResponse, summary="Service health (process is up)")
def health(settings: Annotated[Settings, Depends(get_settings)]) -> HealthResponse:
    return HealthResponse(status="ok", service=SERVICE_NAME, api_version=API_VERSION, app_version=__version__,
                          environment=settings.environment)


@router.get("/liveness", response_model=LivenessResponse, summary="Liveness probe (never touches artifacts)")
def liveness() -> LivenessResponse:
    return LivenessResponse(status="alive")


@router.get("/readiness", response_model=ReadinessResponse, responses={503: {"model": ReadinessResponse}},
            summary="Readiness: locked artifacts verified and every capability loaded")
def readiness(services: Annotated[Services, Depends(get_services)]) -> JSONResponse:
    report = services.adapter.readiness()
    body = ReadinessResponse(
        ready=report.ready,
        checks=[ReadinessCheck(name=c.name, status="ok" if c.ok else "unavailable", detail=c.detail)
                for c in report.checks],
        details=dict(report.details) or None)
    return JSONResponse(body.model_dump(mode="json"), status_code=200 if report.ready else 503)
