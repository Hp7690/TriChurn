"""MLflow experiment tracking for the EXISTING Phase 2 model. Nothing is trained, recomputed or replaced.

Metrics are the values the Phase 2 pipeline already stored in the artifact's sidecar (``metrics.test`` - the single
held-out final evaluation). Parameters are only facts present in that sidecar; anything absent is not logged.
"""
from __future__ import annotations

import json
import math
import tempfile
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from mlops._client import ensure_experiment, get_client
from mlops.config import MlopsSettings
from mlops.errors import ModelIntegrityError, RegistryError
from mlops.integrity import require_verified, sha256_file

# MLflow metric name -> (sidecar block, sidecar key)
METRIC_SOURCES: dict[str, tuple[str, str]] = {
    "roc_auc": ("probability_metrics", "roc_auc"), "pr_auc": ("probability_metrics", "pr_auc"),
    "brier_score": ("probability_metrics", "brier"), "log_loss": ("probability_metrics", "log_loss"),
    "accuracy": ("threshold_metrics", "accuracy"), "precision": ("threshold_metrics", "precision"),
    "recall": ("threshold_metrics", "recall"), "f1": ("threshold_metrics", "f1"),
}


@dataclass(frozen=True)
class TrackingResult:
    run_id: str
    experiment_id: str
    experiment_name: str
    reused: bool
    artifact_sha256: str
    metrics: dict[str, float]


def load_sidecar(settings: MlopsSettings) -> dict[str, Any]:
    try:
        data = json.loads(settings.metadata_file.read_text(encoding="utf-8"))
    except (OSError, ValueError) as exc:
        raise ModelIntegrityError(settings.metadata_file.name, "metadata_unreadable") from exc
    if not isinstance(data, dict):
        raise ModelIntegrityError(settings.metadata_file.name, "metadata_unreadable")
    return data


def extract_metrics(sidecar: dict[str, Any]) -> dict[str, float]:
    """The eight tracked metrics, read (never recomputed) from the sidecar's ``metrics.test`` block."""
    test = (sidecar.get("metrics") or {}).get("test")
    if not isinstance(test, dict):
        raise RegistryError("The model metadata has no 'metrics.test' block; refusing to invent metrics.")
    out: dict[str, float] = {}
    for name, (block, key) in METRIC_SOURCES.items():
        value = (test.get(block) or {}).get(key)
        if isinstance(value, bool) or not isinstance(value, int | float) or not math.isfinite(float(value)):
            raise RegistryError(f"The model metadata has no finite value for metric '{name}'.")
        out[name] = float(value)
    return out


def extract_params(sidecar: dict[str, Any], settings: MlopsSettings) -> dict[str, str]:
    """Only facts that exist in the sidecar. Absent facts are omitted, not defaulted."""
    params: dict[str, Any] = {"registered_model_name": settings.model_name}
    threshold = sidecar.get("threshold") or {}
    dataset = sidecar.get("dataset") or {}
    splits = dataset.get("split_sizes") or {}
    flat = {
        "model_name": sidecar.get("model_name"), "model_version": sidecar.get("model_version"),
        "threshold": threshold.get("value"), "threshold_metric": threshold.get("metric"),
        "threshold_source": threshold.get("source"), "random_state": sidecar.get("random_state"),
        "feature_count": sidecar.get("feature_count"), "model_feature_count": sidecar.get("model_feature_count"),
        "target": sidecar.get("target"), "positive_class": sidecar.get("positive_class"),
        "imbalance_strategy": sidecar.get("imbalance_strategy"),
        "calibration_method": (sidecar.get("calibration") or {}).get("method"),
        "dataset_version": dataset.get("version"), "dataset_rows": dataset.get("rows"),
        "split_train": splits.get("train"), "split_validation": splits.get("validation"),
        "split_test": splits.get("test"),
    }
    params.update(flat)
    for key, value in (sidecar.get("hyperparameters") or {}).items():
        params[f"hp_{key}"] = value
    for key, value in (sidecar.get("environment") or {}).items():
        params[f"train_env_{key}"] = value
    return {k: str(v) for k, v in params.items() if v is not None}


def run_tags(sidecar: dict[str, Any], settings: MlopsSettings, sha: str) -> dict[str, str]:
    tags = {"project": "TriChurn", "phase": "8", "model_version": settings.model_version,
            "model_type": "churn_prediction", "status": "production", "artifact_sha256": sha,
            "metrics_split": "test", "metrics_source": "phase2_artifact_sidecar",
            "source": "existing_phase2_artifact", "integrity_verified_before": "true"}
    if sidecar.get("trained_at"):
        tags["trained_at"] = str(sidecar["trained_at"])
    return tags


def _find_finished_run(client: Any, experiment_id: str, sha: str) -> str | None:
    runs = client.search_runs([experiment_id], max_results=1, order_by=["attributes.start_time DESC"],
                              filter_string=f"tags.artifact_sha256 = '{sha}' and tags.phase = '8' "
                                            "and attributes.status = 'FINISHED' "
                                            "and tags.integrity_verified_after = 'true'")
    return runs[0].info.run_id if runs else None


def log_model_run(settings: MlopsSettings, *, force: bool = False) -> TrackingResult:
    """Verify -> log params/metrics/tags -> log the artifact -> re-verify (source AND the stored copy).

    Idempotent: if a finished, verified run for the same digest exists it is reused (``force=True`` logs a new one).
    A digest/version mismatch raises ``ModelIntegrityError`` BEFORE any run is created.
    """
    before = require_verified(settings.model_file, settings.model_sha256, metadata_path=settings.metadata_file,
                              expected_version=settings.model_version)
    sidecar = load_sidecar(settings)
    metrics, params = extract_metrics(sidecar), extract_params(sidecar, settings)
    try:
        client = get_client(settings, create_local_store=True)
        experiment_id = ensure_experiment(client, settings)
        if not force:
            existing = _find_finished_run(client, experiment_id, before.expected_sha256)
            if existing:
                return TrackingResult(existing, experiment_id, settings.experiment_name, True,
                                      before.expected_sha256, metrics)
        from mlflow.entities import Metric, Param, RunTag  # noqa: PLC0415
        run = client.create_run(experiment_id, run_name=f"churn-model-{settings.model_version}",
                                tags=run_tags(sidecar, settings, before.expected_sha256))
        run_id = run.info.run_id
        try:
            now = int(time.time() * 1000)
            client.log_batch(run_id, metrics=[Metric(k, v, now, 0) for k, v in metrics.items()],
                             params=[Param(k, v) for k, v in params.items()])
            client.log_artifact(run_id, str(settings.model_file), "model")
            client.log_artifact(run_id, str(settings.metadata_file), "model")
            after = require_verified(settings.model_file, settings.model_sha256,        # the source was not altered
                                     metadata_path=settings.metadata_file, expected_version=settings.model_version)
            with tempfile.TemporaryDirectory() as tmp:                                  # the STORED copy is identical
                stored = client.download_artifacts(run_id, f"model/{settings.model_file.name}", tmp)
                if sha256_file(Path(stored)) != after.expected_sha256:
                    raise ModelIntegrityError(settings.model_file.name, "sha256_mismatch")
            client.log_batch(run_id, tags=[RunTag("integrity_verified_after", "true"),
                                           RunTag("logged_artifact_sha256_verified", "true")])
            client.set_terminated(run_id, "FINISHED")
        except BaseException:
            client.set_terminated(run_id, "FAILED")
            raise
    except (ModelIntegrityError, RegistryError):
        raise
    except Exception as exc:                                  # noqa: BLE001  (MLflow/IO errors: never leak internals)
        raise RegistryError(f"MLflow tracking failed ({type(exc).__name__}).") from exc
    return TrackingResult(run_id, experiment_id, settings.experiment_name, False, before.expected_sha256, metrics)
