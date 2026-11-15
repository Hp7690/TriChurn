"""Read-only model lifecycle status (integrity + optional registry state). Used by the API; never raises."""
from __future__ import annotations

from concurrent.futures import ThreadPoolExecutor
from concurrent.futures import TimeoutError as FutureTimeout
from typing import Any

from mlops.config import MlopsSettings
from mlops.integrity import verify_model_artifact


def _registry(settings: MlopsSettings, timeout: float) -> dict[str, Any]:
    from mlops.registry import registry_snapshot  # noqa: PLC0415   (lazy: mlflow only if the registry is queried)
    pool = ThreadPoolExecutor(max_workers=1)
    try:
        return pool.submit(registry_snapshot, settings).result(timeout=timeout)
    except FutureTimeout:
        return {"status": "unavailable", "model_name": settings.model_name, "error_type": "Timeout"}
    finally:
        pool.shutdown(wait=False, cancel_futures=True)


def model_status(settings: MlopsSettings, *, check_registry: bool = False,
                 registry_timeout: float = 10.0) -> dict[str, Any]:
    report = verify_model_artifact(settings.model_file, settings.model_sha256, metadata_path=settings.metadata_file,
                                   expected_version=settings.model_version)
    if report.ok:
        status = "verified"
    elif report.reason == "missing":
        status = "model_missing"
    else:
        status = "integrity_failed"
    if not check_registry:
        registry: dict[str, Any] = {"status": "not_configured", "model_name": settings.model_name}
    else:
        registry = _registry(settings, registry_timeout)
    return {"status": status, "model_version": settings.model_version, "integrity": report.to_dict(),
            "registry": registry}
