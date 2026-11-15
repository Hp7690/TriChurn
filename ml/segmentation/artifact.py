"""Phase 5 segmentation artifact: joblib bundle + JSON metadata sidecar with the bundle's SHA-256.

Separate from (and never overwriting) the Phase 2 churn artifact: different file name, ``kind: segmentation``.
The loader hashes the bytes, compares with the sidecar and only then deserialises those same bytes (the Phase 3
approach: no check/use gap).
"""
from __future__ import annotations

import hashlib
import io
import json
import platform
from dataclasses import asdict, dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import joblib
import numpy as np
import pandas as pd
import sklearn

from ml.errors import ArtifactIntegrityError
from ml.pipelines.ingestion import file_sha256
from ml.pipelines.serialization import ArtifactPaths, resolve_dir
from ml.segmentation.clustering import SegmentationModel
from ml.segmentation.schemas import PROFILING_NOTE, KSelection, SegmentationConfig, SegmentProfile

BUNDLE_SCHEMA = 1
KIND = "segmentation"
_SHA_LEN = 64


def fingerprint(obj: Any) -> str:
    """SHA-256 of a canonical JSON rendering (used for configuration provenance)."""
    return hashlib.sha256(json.dumps(obj, sort_keys=True, default=str).encode()).hexdigest()


def build_metadata(
    model: SegmentationModel, cfg: SegmentationConfig, seed: int, selection: KSelection | None,
    profiles: list[SegmentProfile], *, dataset_info: dict, split_sizes: dict, n_train_customers: int,
    business_config: dict, churn_model_sha256: str | None, trained_at: str | None = None,
) -> dict[str, Any]:
    centers = model.centers_original_units()
    return {
        "kind": KIND, "model_name": "kmeans_segmentation", "model_version": cfg.model_version,
        "trained_at": trained_at or datetime.now(UTC).isoformat(timespec="seconds"),
        "random_state": seed, "selected_k": model.k,
        "k_selection": None if selection is None else selection.to_dict(),
        "feature_names": list(model.feature_names), "feature_count": len(model.feature_names),
        "excluded_from_clustering": {"always": ["dataset target", "dataset id column", *cfg.features.forbidden],
                                     "note": "churn probability and every Phase 4 output are used only to PROFILE "
                                             "segments after clustering"},
        "preprocessing": {"imputation": cfg.imputation, "scaling": cfg.scaling,
                          "steps": [name for name, _ in model.preprocessor.steps]},
        "kmeans": asdict(cfg.kmeans),
        "centroids_original_units": [dict(zip(model.feature_names, map(float, row), strict=True))
                                     for row in centers],
        "training": {"fit_split": "train", "n_customers": n_train_customers, "uses_target": False,
                     "uses_churn_probability": False, "uses_validation": False, "uses_test": False,
                     "kmeans_inertia": float(model.kmeans.inertia_), "kmeans_iterations": int(model.kmeans.n_iter_)},
        "dataset": {**dataset_info, "split_sizes": split_sizes},
        "configuration": asdict(cfg),
        "segment_catalog": [{"segment_id": p.segment_id, "segment_name": p.segment_name,
                             "customer_count": p.customer_count, "priority_rank": p.priority_rank,
                             "priority_tier": p.priority_tier} for p in profiles],
        "profiling_provenance": {"business_config_sha256": fingerprint(business_config),
                                 "churn_model_sha256": churn_model_sha256, "note": PROFILING_NOTE},
        "environment": {"python": platform.python_version(), "scikit_learn": sklearn.__version__,
                        "pandas": pd.__version__, "numpy": np.__version__},
    }


def save_segmentation_artifact(model: SegmentationModel, metadata: dict, directory: str | Path, name: str
                               ) -> ArtifactPaths:
    out = resolve_dir(directory)
    out.mkdir(parents=True, exist_ok=True)
    stem = f"{name}_v{metadata['model_version']}"
    model_path, meta_path = out / f"{stem}.joblib", out / f"{stem}.metadata.json"
    joblib.dump({"schema_version": BUNDLE_SCHEMA, "kind": KIND, "model": model, "metadata": metadata},
                model_path, compress=3)
    digest = file_sha256(model_path)
    meta_path.write_text(json.dumps({**metadata, "artifact_file": model_path.name, "artifact_sha256": digest},
                                    indent=2, default=str))
    return ArtifactPaths(model_path, meta_path, digest)


@dataclass
class VerifiedSegmentation:
    model: SegmentationModel
    metadata: dict          # embedded metadata
    sidecar: dict           # trusted sidecar (includes artifact_sha256)
    sha256: str
    path: Path

    @property
    def segment_names(self) -> dict[int, str]:
        return {int(c["segment_id"]): c["segment_name"] for c in self.metadata["segment_catalog"]}


def load_verified_segmentation_artifact(model_path: str | Path, metadata_path: str | Path | None = None,
                                        expected_sha256: str | None = None) -> VerifiedSegmentation:
    """bytes -> SHA-256 -> compare with sidecar -> (only then) deserialise -> cross-check embedded metadata."""
    model_path = Path(model_path)
    meta_path = Path(metadata_path) if metadata_path else model_path.with_name(f"{model_path.stem}.metadata.json")
    try:
        raw = model_path.read_bytes()
        sidecar = json.loads(meta_path.read_text(encoding="utf-8"))
    except (OSError, ValueError) as exc:
        raise ArtifactIntegrityError(f"Cannot read segmentation artifact or its metadata: {exc}") from exc
    expected = (expected_sha256 or (sidecar.get("artifact_sha256") if isinstance(sidecar, dict) else "") or ""
                ).strip().lower()
    if len(expected) != _SHA_LEN:
        raise ArtifactIntegrityError("No valid SHA-256 digest is available in the segmentation metadata.")
    actual = hashlib.sha256(raw).hexdigest()
    if actual != expected:
        raise ArtifactIntegrityError(
            f"Segmentation artifact SHA-256 mismatch for '{model_path.name}': expected {expected[:12]}..., computed "
            f"{actual[:12]}.... The file was modified or does not belong to this metadata; it was NOT loaded.")
    try:
        bundle = joblib.load(io.BytesIO(raw))
        model, embedded = bundle["model"], bundle["metadata"]
        valid = bundle.get("schema_version") == BUNDLE_SCHEMA and bundle.get("kind") == KIND
    except Exception as exc:  # noqa: BLE001 - any failure to restore a hash-verified file is an artifact problem
        raise ArtifactIntegrityError(f"The verified segmentation artifact could not be restored: {exc}") from exc
    if not valid or not isinstance(model, SegmentationModel):
        raise ArtifactIntegrityError("The file is not a Phase 5 segmentation artifact.")
    for what in ("model_version", "feature_names", "selected_k", "random_state", "segment_catalog"):
        if embedded.get(what) != sidecar.get(what):
            raise ArtifactIntegrityError(f"Artifact and metadata disagree on {what}.")
    return VerifiedSegmentation(model, embedded, sidecar, actual, model_path)
