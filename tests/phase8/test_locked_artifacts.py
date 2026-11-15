"""Regression guards: locked Phase 2 / Phase 5 artifacts, baseline metrics and threshold are untouched."""
from __future__ import annotations

import json

from mlops import MlopsSettings
from mlops.integrity import sha256_file
from mlops.tracking import extract_metrics, log_model_run
from tests.phase8.conftest import (
    LOCKED,
    LOCKED_PHASE5_SHA256,
    METADATA,
    MODEL,
    ROOT,
    SEGMENTATION,
    SPEC_METRICS,
    store_settings,
)


def test_phase2_and_phase5_digests_are_the_locked_ones():
    assert sha256_file(MODEL) == LOCKED
    assert sha256_file(SEGMENTATION) == LOCKED_PHASE5_SHA256


def test_models_directory_contains_exactly_the_four_locked_files():
    assert sorted(p.name for p in (ROOT / "models").iterdir()) == [
        "trichurn_churn_model_v2.0.0.joblib", "trichurn_churn_model_v2.0.0.metadata.json",
        "trichurn_segmentation_v5.0.0.joblib", "trichurn_segmentation_v5.0.0.metadata.json"]


def test_baseline_metrics_threshold_and_version_are_preserved():
    meta = json.loads(METADATA.read_text())
    assert meta["artifact_sha256"] == LOCKED and meta["model_version"] == "2.0.0"
    assert meta["threshold"]["value"] == 0.34
    assert {k: round(v, 4) for k, v in extract_metrics(meta).items()} == SPEC_METRICS


def test_phase5_artifact_is_still_the_locked_k3_seed42_segmentation():
    from ml.segmentation import load_verified_segmentation_artifact
    loaded = load_verified_segmentation_artifact(SEGMENTATION)
    assert loaded.sha256 == LOCKED_PHASE5_SHA256 and loaded.model.k == 3
    assert list(loaded.model.feature_names) == ["tenure", "MonthlyCharges", "TotalCharges", "service_count",
                                                "contract_risk"]
    assert loaded.metadata["random_state"] == 42


def test_running_the_full_phase8_flow_leaves_every_locked_file_byte_identical(tmp_path):
    from mlops.registry import register_verified_model
    before = {p.name: sha256_file(p) for p in (ROOT / "models").iterdir()}
    stat = {p.name: p.stat().st_mtime_ns for p in (ROOT / "models").iterdir()}
    store = store_settings(tmp_path / "s")
    register_verified_model(store, log_model_run(store).run_id)
    assert {p.name: sha256_file(p) for p in (ROOT / "models").iterdir()} == before
    assert {p.name: p.stat().st_mtime_ns for p in (ROOT / "models").iterdir()} == stat


def test_default_settings_pin_the_locked_digest():
    assert MlopsSettings().model_sha256 == LOCKED
