from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Depends

from app.api.dependencies import get_settings
from app.core.config import Settings
from app.schemas.model_lifecycle import ModelLifecycleResponse
from app.services.model_lifecycle import describe_model_lifecycle

router = APIRouter(tags=["model"])


@router.get("/model/lifecycle", response_model=ModelLifecycleResponse,
            summary="Model version, artifact integrity and registry status (read-only)")
def model_lifecycle(settings: Annotated[Settings, Depends(get_settings)]) -> ModelLifecycleResponse:
    return ModelLifecycleResponse(**describe_model_lifecycle(settings.project_root))
