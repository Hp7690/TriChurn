"""Shared MLflow plumbing. ``mlflow`` is imported lazily so that importing the rest of ``mlops`` (and the API) never
requires it: ordinary prediction must keep working when MLflow is absent or unreachable."""
from __future__ import annotations

import os
from typing import Any

from mlops.config import MlopsSettings
from mlops.errors import RegistryError


def import_mlflow() -> Any:
    os.environ.setdefault("MLFLOW_ENABLE_ARTIFACTS_PROGRESS_BAR", "false")      # keep CLI/test output clean
    try:
        import mlflow  # noqa: PLC0415
    except ImportError as exc:
        raise RegistryError("mlflow is not installed (pip install -r requirements-phase8.txt).") from exc
    return mlflow


def get_client(settings: MlopsSettings, *, create_local_store: bool = False) -> Any:
    """An ``MlflowClient`` bound to the configured URI. No global mlflow state is touched."""
    import_mlflow()
    from mlflow.tracking import MlflowClient  # noqa: PLC0415
    if create_local_store and not settings.tracking_uri:            # default local SQLite store lives under the project
        settings.local_store.mkdir(parents=True, exist_ok=True)
    uri = settings.effective_tracking_uri
    return MlflowClient(tracking_uri=uri, registry_uri=uri)


def ensure_experiment(client: Any, settings: MlopsSettings) -> str:
    from mlflow.exceptions import MlflowException  # noqa: PLC0415
    exp = client.get_experiment_by_name(settings.experiment_name)
    if exp is None:
        try:
            return str(client.create_experiment(settings.experiment_name,
                                                artifact_location=settings.effective_artifact_location))
        except MlflowException:                                      # lost a creation race: read it back
            exp = client.get_experiment_by_name(settings.experiment_name)
            if exp is None:
                raise RegistryError("Could not create the MLflow experiment.") from None
    if exp.lifecycle_stage != "active":
        raise RegistryError("The MLflow experiment exists but is deleted; restore or rename it.")
    return str(exp.experiment_id)
