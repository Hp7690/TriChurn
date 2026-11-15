"""MLflow Model Registry integration for the EXISTING, integrity-verified Phase 2 model.

Registered versions point at the raw verified ``.joblib`` (+ its sidecar) stored as run artifacts - this is an
artifact registry, not an MLflow pyfunc flavour (see docs/phase8.md, Known limitations). A model is only registered /
promoted after it matches the locked digest; a new or unverified model is never promoted automatically.
"""
from __future__ import annotations

import tempfile
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from mlops._client import get_client, import_mlflow
from mlops.config import PRODUCTION_ALIAS, MlopsSettings
from mlops.errors import ModelIntegrityError, RegistryError
from mlops.integrity import require_verified, sha256_file


@dataclass(frozen=True)
class RegistrationResult:
    model_name: str
    registry_version: str               # MLflow's internal numeric version
    semantic_version: str               # the project's version (e.g. 2.0.0), stored as a tag
    run_id: str
    reused: bool
    alias: str
    artifact_sha256: str


def _is_missing(exc: Exception) -> bool:
    """True only for MLflow's 'does not exist' error. Connection/permission errors are NOT 'missing'."""
    return getattr(exc, "error_code", None) == "RESOURCE_DOES_NOT_EXIST"


def model_tags(settings: MlopsSettings, sha: str) -> dict[str, str]:
    return {"project": "TriChurn", "phase": "8", "model_version": settings.model_version,
            "model_type": "churn_prediction", "status": "production", "artifact_sha256": sha}


def _verify_stored_copy(client: Any, run_id: str, settings: MlopsSettings, sha: str) -> None:
    """The bytes that will be promoted (the run's stored copy) must hash to the locked digest."""
    with tempfile.TemporaryDirectory() as tmp:
        try:
            stored = client.download_artifacts(run_id, f"model/{settings.model_file.name}", tmp)
        except Exception as exc:                                  # noqa: BLE001
            raise ModelIntegrityError(settings.model_file.name, "missing") from exc
        if sha256_file(Path(stored)) != sha:
            raise ModelIntegrityError(settings.model_file.name, "sha256_mismatch")


def register_verified_model(settings: MlopsSettings, run_id: str) -> RegistrationResult:
    """Register (idempotently) and set the ``production`` alias - only for a verified model."""
    report = require_verified(settings.model_file, settings.model_sha256, metadata_path=settings.metadata_file,
                              expected_version=settings.model_version)
    sha = report.expected_sha256
    try:
        client = get_client(settings, create_local_store=True)
        _verify_stored_copy(client, run_id, settings, sha)
        from mlflow.exceptions import MlflowException  # noqa: PLC0415
        try:
            client.get_registered_model(settings.model_name)
        except MlflowException as exc:
            if not _is_missing(exc):
                raise
            client.create_registered_model(
                settings.model_name, tags={"project": "TriChurn", "model_type": "churn_prediction"},
                description="TriChurn churn model (existing Phase 2 artifact; registered by Phase 8, not retrained).")
        existing = next((v for v in client.search_model_versions(f"name='{settings.model_name}'")
                         if (v.tags or {}).get("artifact_sha256") == sha), None)
        reused = existing is not None
        version = existing or client.create_model_version(
            settings.model_name, source=f"runs:/{run_id}/model", run_id=run_id, tags=model_tags(settings, sha),
            description=f"Existing Phase 2 churn model {settings.model_version}; SHA-256 {sha}.")
        client.set_registered_model_alias(settings.model_name, PRODUCTION_ALIAS, str(version.version))
    except (ModelIntegrityError, RegistryError):
        raise
    except Exception as exc:                                  # noqa: BLE001
        raise RegistryError(f"Model registration failed ({type(exc).__name__}).") from exc
    return RegistrationResult(settings.model_name, str(version.version), settings.model_version, run_id, reused,
                              PRODUCTION_ALIAS, sha)


def fetch_verified_model(settings: MlopsSettings, dest: Path, *, alias: str = PRODUCTION_ALIAS) -> Path:
    """Download the aliased registry version into ``dest`` and verify it. Returns the verified ``.joblib`` path.

    Raises ``ModelIntegrityError`` if the stored bytes do not match the pinned digest (nothing is deserialised)."""
    mlflow = import_mlflow()
    try:
        client = get_client(settings)
        version = client.get_model_version_by_alias(settings.model_name, alias)
        uri = client.get_model_version_download_uri(settings.model_name, version.version)
        folder = Path(mlflow.artifacts.download_artifacts(artifact_uri=uri, dst_path=str(dest),
                                                          tracking_uri=settings.effective_tracking_uri))
    except Exception as exc:                                  # noqa: BLE001
        raise RegistryError(f"Model could not be fetched from the registry ({type(exc).__name__}).") from exc
    model = folder / settings.model_file.name
    require_verified(model, settings.model_sha256, metadata_path=folder / settings.metadata_file.name,
                     expected_version=settings.model_version)
    return model


def registry_snapshot(settings: MlopsSettings) -> dict[str, Any]:
    """Read-only registry state. Never raises: every failure becomes a status string."""
    try:
        import_mlflow()
    except RegistryError:
        return {"status": "mlflow_not_installed", "model_name": settings.model_name}
    try:
        from mlflow.exceptions import MlflowException  # noqa: PLC0415
        client = get_client(settings)
        try:
            client.get_registered_model(settings.model_name)
        except MlflowException as exc:
            if not _is_missing(exc):
                raise                                              # unreachable/denied is NOT "not registered"
            return {"status": "not_registered", "model_name": settings.model_name}
        try:
            prod = client.get_model_version_by_alias(settings.model_name, PRODUCTION_ALIAS)
        except MlflowException as exc:
            if not _is_missing(exc):
                raise
            return {"status": "registered_no_production_alias", "model_name": settings.model_name}
        tags = prod.tags or {}
        return {"status": "registered", "model_name": settings.model_name, "registry_version": str(prod.version),
                "semantic_version": tags.get("model_version"), "alias": PRODUCTION_ALIAS,
                "artifact_sha256": tags.get("artifact_sha256"),
                "matches_pinned_sha256": tags.get("artifact_sha256") == settings.model_sha256}
    except Exception as exc:                                  # noqa: BLE001
        return {"status": "unavailable", "model_name": settings.model_name, "error_type": type(exc).__name__}
