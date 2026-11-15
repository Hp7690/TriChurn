"""/api/v1/experience: availability, tenure lifecycle proxy, upload validation and module status (Phase 13).

``register_experience(app, settings)`` is the single integration point: it builds the service from configuration and
mounts the router. It never raises for a bad experience configuration (the existing API must keep starting); instead the
service reports VALIDATION_FAILED.
"""

from __future__ import annotations

import logging
import os
from collections.abc import Callable, Mapping
from datetime import datetime
from pathlib import Path
from typing import Annotated, Any

from fastapi import APIRouter, Depends, FastAPI, Query, Request

from app.core.errors import ApiError, ErrorCode
from app.schemas.experience import (
    AvailabilityResponse,
    DataQualityRequest,
    DataQualityResponse,
    LifecycleResponse,
    ModuleStatusResponse,
    SurveyValidationRequest,
    ValidationRequest,
    ValidationResponse,
)
from app.services.experience_service import ExperienceService, payload_too_large
from trichurn_experience.config import ExperienceConfigError, load_experience_config
from trichurn_experience.schemas import DatasetKind
from trichurn_experience.sentiment import SentimentModel

logger = logging.getLogger("trichurn.experience")

router = APIRouter(prefix="/experience", tags=["experience"])
ERR = {
    413: {"description": "Content exceeds the configured size limit."},
    422: {"description": "Invalid request."},
    503: {"description": "Experience module unavailable."},
}


def get_experience_service(request: Request) -> ExperienceService:
    service = getattr(request.app.state, "experience_service", None)
    if service is None:
        raise ApiError(ErrorCode.CAPABILITY_UNAVAILABLE, "The 'experience' capability is currently unavailable.", 503)
    return service


Service = Annotated[ExperienceService, Depends(get_experience_service)]


def enforce_body_limit(request: Request, service: Service) -> None:
    """Reject oversized bodies from the Content-Length header before FastAPI reads them (the service re-checks)."""
    declared = request.headers.get("content-length")
    if declared is not None:
        try:
            too_big = int(declared) > service.max_body_bytes()
        except ValueError:
            raise ApiError(ErrorCode.INVALID_INPUT, "Invalid Content-Length header.", 422) from None
        if too_big:
            raise payload_too_large()


BodyLimit = Depends(enforce_body_limit)


# ------------------------------------------------------------------------------------------------ read endpoints
@router.get("/availability", response_model=AvailabilityResponse, summary="Availability of every experience module")
def availability(service: Service) -> dict[str, Any]:
    return service.availability()


@router.get(
    "/lifecycle", response_model=LifecycleResponse, summary="Tenure-based lifecycle PROXY (not an event-based journey)"
)
def lifecycle(service: Service) -> dict[str, Any]:
    return service.lifecycle()


def _status(name: str):
    def handler(service: Service) -> dict[str, Any]:
        return service.module_status(name)

    return handler


for _name, _summary in (
    ("sentiment", "Sentiment intelligence status"),
    ("complaints", "Complaint intelligence status"),
    ("journey", "Customer journey status"),
):
    router.add_api_route(
        f"/{_name}/status",
        _status(_name),
        methods=["GET"],
        response_model=ModuleStatusResponse,
        summary=_summary,
        name=f"{_name}_status",
    )


def _survey_status(name: str):
    def handler(
        service: Service,
        period_start: Annotated[str | None, Query(max_length=40, description="ISO 8601 date or date-time")] = None,
        period_end: Annotated[str | None, Query(max_length=40, description="ISO 8601 date or date-time")] = None,
    ) -> dict[str, Any]:
        return service.module_status(name, period_start=period_start, period_end=period_end)

    return handler


for _name, _summary in (
    ("nps", "NPS status and score (real survey data only)"),
    ("csat", "CSAT status and score (real survey data only)"),
):
    router.add_api_route(
        f"/{_name}/status",
        _survey_status(_name),
        methods=["GET"],
        response_model=ModuleStatusResponse,
        summary=_summary,
        name=f"{_name}_status",
    )


# ------------------------------------------------------------------------------------------------ validation endpoints
def _validator(kind: DatasetKind):
    def handler(body: ValidationRequest, service: Service) -> dict[str, Any]:
        return service.validate(kind, body.format, body.content)

    return handler


for _path, _kind, _summary in (
    ("validate-feedback", DatasetKind.FEEDBACK, "Validate a feedback file (not stored)"),
    ("validate-tickets", DatasetKind.TICKETS, "Validate a complaint/ticket file (not stored)"),
    ("validate-events", DatasetKind.EVENTS, "Validate a journey event file (not stored)"),
):
    router.add_api_route(
        f"/{_path}",
        _validator(_kind),
        methods=["POST"],
        response_model=ValidationResponse,
        responses=ERR,
        summary=_summary,
        dependencies=[BodyLimit],
        name=_path.replace("-", "_"),
    )


@router.post(
    "/validate-survey",
    response_model=ValidationResponse,
    responses=ERR,
    dependencies=[BodyLimit],
    summary="Validate an NPS or CSAT survey file (not stored)",
)
def validate_survey(body: SurveyValidationRequest, service: Service) -> dict[str, Any]:
    return service.validate(DatasetKind(body.survey_type), body.format, body.content)


@router.post(
    "/data-quality",
    response_model=DataQualityResponse,
    responses=ERR,
    dependencies=[BodyLimit],
    summary="Validation report plus completeness, validity and duplicate rates for an upload (not stored)",
)
def data_quality(body: DataQualityRequest, service: Service) -> dict[str, Any]:
    return service.data_quality(DatasetKind(body.dataset), body.format, body.content)


# ------------------------------------------------------------------------------------------------ integration hook
def build_experience_service(
    settings: Any,
    *,
    config_path: str | Path | None = None,
    probability_provider: Callable[[], Mapping[str, float]] | None = None,
    sentiment_model: SentimentModel | None = None,
    clock: Callable[[], datetime] | None = None,
) -> ExperienceService:
    """Build the service from ``Settings``. A malformed experience configuration yields a VALIDATION_FAILED service."""
    root = Path(getattr(settings, "project_root", Path.cwd()))
    csv_setting = getattr(settings, "dataset_csv_path", "ml/data/raw/telco_churn.csv")
    resolver = getattr(settings, "resolve", None)
    customer_csv = Path(resolver(csv_setting)) if callable(resolver) else root / csv_setting
    cfg_file = config_path or os.environ.get("TRICHURN_EXPERIENCE_CONFIG") or "configs/experience.yaml"
    cfg_path = Path(cfg_file) if Path(cfg_file).is_absolute() else root / cfg_file
    try:
        cfg, error = load_experience_config(cfg_path), None
    except ExperienceConfigError as exc:
        logger.error("Experience configuration invalid: %s", exc)
        cfg, error = None, str(exc)
    return ExperienceService(
        cfg,
        project_root=root,
        customer_csv=customer_csv,
        config_error=error,
        probability_provider=probability_provider,
        sentiment_model=sentiment_model,
        clock=clock,
    )


def register_experience(app: FastAPI, settings: Any | None = None, **kwargs: Any) -> ExperienceService:
    """Mount /api/v1/experience on ``app``. Additive: touches only ``app.state.experience_service`` and one router."""
    settings = settings if settings is not None else getattr(app.state, "settings", None)
    service = build_experience_service(settings, **kwargs)
    app.state.experience_service = service
    prefix = "/api/v1"
    try:
        from app.core.config import API_PREFIX  # noqa: PLC0415 - follow the host project's prefix when available

        prefix = API_PREFIX
    except ImportError:  # pragma: no cover - host without app.core.config
        pass
    app.include_router(router, prefix=prefix)
    return service
