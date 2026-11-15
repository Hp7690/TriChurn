"""Fixtures for the Phase 8 tests. Every MLflow store lives in pytest's tmp_path: nothing is written to the project."""
from __future__ import annotations

import shutil
from pathlib import Path

import pytest

from mlops.config import LOCKED_PHASE2_SHA256, MlopsSettings

ROOT = Path(__file__).resolve().parents[2]
MODEL = ROOT / "models" / "trichurn_churn_model_v2.0.0.joblib"
METADATA = ROOT / "models" / "trichurn_churn_model_v2.0.0.metadata.json"
SEGMENTATION = ROOT / "models" / "trichurn_segmentation_v5.0.0.joblib"
LOCKED_PHASE5_SHA256 = "38423c9cf19b05aa35b72acd44ea3a8af4c3775a1e6cf2bb739ee1972dc05927"
LOCKED = LOCKED_PHASE2_SHA256
# The eight baseline numbers given in the Phase 8 specification (4 decimal places).
SPEC_METRICS = {"roc_auc": 0.8492, "pr_auc": 0.6412, "brier_score": 0.1355, "log_loss": 0.4107,
                "accuracy": 0.7711, "precision": 0.5503, "recall": 0.7429, "f1": 0.6322}


def store_settings(base: Path, **overrides) -> MlopsSettings:
    base.mkdir(parents=True, exist_ok=True)
    return MlopsSettings(tracking_uri=f"sqlite:///{(base / 'mlflow.db').as_posix()}",
                         artifact_location=(base / "artifacts").resolve().as_uri(), tracking_configured=True,
                         **overrides)


@pytest.fixture
def settings(tmp_path: Path) -> MlopsSettings:
    return store_settings(tmp_path / "store")


@pytest.fixture
def tampered_settings(tmp_path: Path) -> MlopsSettings:
    """Settings that point at a copy of the model with ONE flipped byte (and its untouched sidecar)."""
    bad = tmp_path / "bad"
    bad.mkdir()
    raw = bytearray(MODEL.read_bytes())
    raw[len(raw) // 2] ^= 0xFF
    (bad / MODEL.name).write_bytes(bytes(raw))
    shutil.copy(METADATA, bad / METADATA.name)
    return store_settings(tmp_path / "store", model_path=str(bad / MODEL.name))


def file_state(path: Path) -> tuple[int, int, bytes]:
    stat = path.stat()
    return stat.st_size, stat.st_mtime_ns, path.read_bytes()
