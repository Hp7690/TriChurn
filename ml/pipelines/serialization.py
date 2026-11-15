"""Phase 2 - model serialization (joblib) with a JSON metadata sidecar.

The ``.joblib`` bundle is self-contained: the fitted, calibrated pipeline (which accepts RAW customer
records - coercion, feature engineering, imputation, scaling and encoding are inside it), the decision
threshold, and the metadata. The ``.metadata.json`` sidecar repeats the metadata in readable form and adds
the artifact's SHA-256. Paths are resolved relative to the project root; nothing machine-specific is stored.
"""
from __future__ import annotations

import json
import platform
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import joblib
import numpy as np
import pandas as pd
import sklearn
import xgboost

from ml.config import ROOT
from ml.pipelines.final_evaluation import FinalEvaluation, LockedModel
from ml.pipelines.ingestion import DatasetSpec, file_sha256

BUNDLE_SCHEMA = 1


def resolve_dir(directory: str | Path) -> Path:
    """Relative directories are anchored at the project root (never at a hard-coded absolute path)."""
    p = Path(directory)
    return p if p.is_absolute() else ROOT / p


def model_feature_names(locked: LockedModel) -> list[str]:
    return [str(n) for n in locked.model.base.named_steps["preprocess"].get_feature_names_out()]


def build_metadata(
    locked: LockedModel, spec: DatasetSpec, final: FinalEvaluation, *, training_cfg: dict, features_cfg: dict,
    opt_cfg: dict, tuning_summary: dict, cv_metrics: dict, validation_metrics: dict, dataset_info: dict,
    split_sizes: dict, trained_at: str | None = None,
) -> dict[str, Any]:
    model_features = model_feature_names(locked)
    return {
        "model_name": locked.model_name,
        "model_version": opt_cfg["model_version"],
        "trained_at": trained_at or datetime.now(UTC).isoformat(timespec="seconds"),
        "feature_names": list(locked.plan.features),          # raw input columns the model expects
        "feature_count": len(locked.plan.features),
        "model_feature_names": model_features,                # after engineering + encoding
        "model_feature_count": len(model_features),
        "target": spec.target, "positive_class": spec.positive_class,
        "imbalance_strategy": locked.imbalance,
        "hyperparameters": locked.params,
        "calibration": {"method": locked.calibration_method, "parameters": locked.calibration_parameters},
        "threshold": {"value": locked.threshold.threshold, "metric": locked.threshold.metric,
                      "source": locked.threshold.source},
        "random_state": locked.seed,
        "training_configuration": {"training": training_cfg, "features": features_cfg, "optimization": opt_cfg},
        "tuning": tuning_summary,
        "metrics": {"cv_train": cv_metrics, "validation": validation_metrics, "test": final.to_dict()},
        "dataset": {**dataset_info, "split_sizes": split_sizes},
        "decision_fingerprint": locked.fingerprint,
        "environment": {"python": platform.python_version(), "scikit_learn": sklearn.__version__,
                        "xgboost": xgboost.__version__, "pandas": pd.__version__, "numpy": np.__version__},
    }


@dataclass
class ArtifactPaths:
    model: Path
    metadata: Path
    sha256: str


def save_artifact(locked: LockedModel, metadata: dict, directory: str | Path, name: str) -> ArtifactPaths:
    out = resolve_dir(directory)
    out.mkdir(parents=True, exist_ok=True)
    stem = f"{name}_v{metadata['model_version']}"
    model_path, meta_path = out / f"{stem}.joblib", out / f"{stem}.metadata.json"
    bundle = {"schema_version": BUNDLE_SCHEMA, "model": locked.model,
              "threshold": float(locked.threshold.threshold), "metadata": metadata}
    joblib.dump(bundle, model_path, compress=3)
    digest = file_sha256(model_path)
    meta_path.write_text(json.dumps({**metadata, "artifact_file": model_path.name, "artifact_sha256": digest},
                                    indent=2, default=str))
    return ArtifactPaths(model_path, meta_path, digest)


class ModelArtifact:
    """A loaded artifact: score raw customer records with the stored calibration and threshold."""

    def __init__(self, bundle: dict):
        if bundle.get("schema_version") != BUNDLE_SCHEMA:
            raise ValueError(f"Unsupported artifact schema {bundle.get('schema_version')!r}.")
        self.model = bundle["model"]
        self.threshold: float = bundle["threshold"]
        self.metadata: dict = bundle["metadata"]

    def predict_proba(self, X: pd.DataFrame) -> np.ndarray:
        """Calibrated P(churn) for each row."""
        return self.model.predict_proba(X)[:, 1]

    def predict(self, X: pd.DataFrame) -> np.ndarray:
        """1 = predicted churn at the stored (validation-optimised) threshold."""
        return (self.predict_proba(X) >= self.threshold).astype(int)


def load_artifact(path: str | Path) -> ModelArtifact:
    return ModelArtifact(joblib.load(path))
