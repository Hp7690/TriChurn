"""Read-only model lifecycle description (Phase 8): artifact integrity + optional MLflow registry state.

Ordinary prediction never depends on this module or on MLflow. The registry is queried ONLY when
``MLFLOW_TRACKING_URI`` is explicitly configured, with a short timeout; any failure becomes a status string.
"""
from __future__ import annotations

from pathlib import Path
from typing import Any

from mlops.config import MlopsSettings
from mlops.errors import MlopsConfigurationError
from mlops.status import model_status


def describe_model_lifecycle(project_root: Path) -> dict[str, Any]:
    try:
        settings = MlopsSettings.from_env(project_root=project_root)
    except MlopsConfigurationError:
        return {"status": "misconfigured", "model_version": None, "integrity": None, "registry": None}
    return model_status(settings, check_registry=settings.tracking_configured)
