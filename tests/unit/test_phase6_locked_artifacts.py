"""Artifact loading/verification (generic loader) and, when the existing project is present, the locked Phase 2/5
facts. The REAL-artifact tests are skipped ONLY when the artifacts do not exist (standalone overlay run)."""
from __future__ import annotations

import hashlib
import json
import threading
from concurrent.futures import ThreadPoolExecutor

import pytest

from app.core.config import (
    LOCKED_PHASE2_SHA256,
    LOCKED_SEGMENTATION_FEATURES,
    Settings,
)
from app.services.artifact_loader import ArtifactLoader, ArtifactSpec, ArtifactUnavailableError, sha256_file

LOCKED_METRICS = {"roc_auc": 0.8492, "pr_auc": 0.6412, "brier": 0.1355, "log_loss": 0.4107}
LOCKED_THRESHOLD_METRICS = {"accuracy": 0.7711, "precision": 0.5503, "recall": 0.7429, "f1": 0.6322}


def test_locked_phase2_digest_constant():
    assert LOCKED_PHASE2_SHA256 == "db399a55f650c6681e1caaf52257f909777e2c5fada3af5911370ddf5b8ff1ad"


# ------------------------------------------------------------------------------------------- generic loader
@pytest.fixture
def artifact(tmp_path):
    path = tmp_path / "secret_dir" / "model.bin"
    path.parent.mkdir()
    path.write_bytes(b"locked-model-bytes" * 1000)
    return path, hashlib.sha256(path.read_bytes()).hexdigest()


def test_sha256_file_streams_correctly(artifact):
    path, digest = artifact
    assert sha256_file(path, chunk_size=7) == digest


def test_verify_statuses(artifact, tmp_path):
    path, digest = artifact
    loader = ArtifactLoader()
    ok = loader.verify(ArtifactSpec("m", path, digest))
    assert (ok.present, ok.verified, ok.sha256, ok.reason) == (True, True, digest, None)
    assert loader.verify(ArtifactSpec("m", path, None)).verified is True            # unpinned: reported, not pinned
    bad = loader.verify(ArtifactSpec("m", path, "0" * 64))
    assert (bad.present, bad.verified, bad.reason) == (True, False, "sha256_mismatch")
    assert loader.verify(ArtifactSpec("m", tmp_path / "nope.bin", digest)).reason == "missing"
    assert loader.verify(ArtifactSpec("m", path.parent, digest)).reason == "missing"      # a directory is not a file


def test_errors_name_the_artifact_and_reason_but_never_the_path(artifact, tmp_path):
    path, _ = artifact
    for spec in (ArtifactSpec("phase2_model", path, "0" * 64), ArtifactSpec("phase2_model", tmp_path / "x", None)):
        with pytest.raises(ArtifactUnavailableError) as exc:
            ArtifactLoader().require_verified(spec)
        assert str(tmp_path) not in str(exc.value) and "secret_dir" not in str(exc.value)
        assert exc.value.name == "phase2_model" and exc.value.reason in {"sha256_mismatch", "missing"}


def test_load_once_loads_a_single_time_even_under_concurrency(artifact):
    path, digest = artifact
    loader, calls = ArtifactLoader(), []

    def slow_loader(p):
        calls.append(p)
        return object()

    spec = ArtifactSpec("m", path, digest)
    with ThreadPoolExecutor(16) as pool:
        results = list(pool.map(lambda _: loader.load_once(spec, slow_loader), range(64)))
    assert len(calls) == 1 and all(r is results[0] for r in results)


def test_load_once_refuses_to_load_an_unverified_artifact(artifact):
    path, _ = artifact
    called = threading.Event()
    with pytest.raises(ArtifactUnavailableError):
        ArtifactLoader().load_once(ArtifactSpec("m", path, "f" * 64), lambda p: called.set())
    assert not called.is_set()


def test_loading_and_verifying_never_modifies_anything(artifact):
    path, digest = artifact
    before = (path.read_bytes(), path.stat().st_mtime_ns, sorted(p.name for p in path.parent.iterdir()))
    loader = ArtifactLoader()
    loader.verify(ArtifactSpec("m", path, digest))
    loader.load_once(ArtifactSpec("m", path, digest), lambda p: p.read_bytes())
    after = (path.read_bytes(), path.stat().st_mtime_ns, sorted(p.name for p in path.parent.iterdir()))
    assert before == after


def test_a_modified_artifact_is_detected_after_it_was_first_hashed(artifact):
    path, digest = artifact
    loader = ArtifactLoader()
    assert loader.verify(ArtifactSpec("m", path, digest)).verified
    path.write_bytes(b"tampered")                                  # size changes, so the digest cache is bypassed
    assert loader.verify(ArtifactSpec("m", path, digest)).reason == "sha256_mismatch"


# ---------------------------------------------------------------------------- real, locked project artifacts
SETTINGS = Settings()
PHASE2 = SETTINGS.resolve(SETTINGS.phase2_model_path)
PHASE5 = SETTINGS.resolve(SETTINGS.phase5_model_path)
needs_phase2 = pytest.mark.skipif(not PHASE2.is_file(), reason="Phase 2 artifact not present (standalone overlay run)")
needs_phase5 = pytest.mark.skipif(not PHASE5.is_file(), reason="Phase 5 artifact not present (standalone overlay run)")


@needs_phase2
def test_real_phase2_artifact_matches_the_locked_digest_and_sidecar():
    assert sha256_file(PHASE2) == LOCKED_PHASE2_SHA256
    sidecar = json.loads(PHASE2.with_name(PHASE2.stem + ".metadata.json").read_text(encoding="utf-8"))
    assert sidecar["artifact_sha256"] == LOCKED_PHASE2_SHA256
    assert ArtifactLoader().verify(ArtifactSpec("phase2_model", PHASE2, LOCKED_PHASE2_SHA256)).verified


@needs_phase2
def test_real_phase2_artifact_carries_the_locked_metrics_and_threshold():
    meta = json.loads(PHASE2.with_name(PHASE2.stem + ".metadata.json").read_text(encoding="utf-8"))
    test = meta["metrics"]["test"]
    for key, value in LOCKED_METRICS.items():
        assert round(test["probability_metrics"][key], 4) == value, key
    for key, value in LOCKED_THRESHOLD_METRICS.items():
        assert round(test["threshold_metrics"][key], 4) == value, key
    assert meta["threshold"]["value"] == 0.34 and meta["model_name"] == "logistic_regression"
    assert meta["model_version"] == "2.0.0" and meta["feature_count"] == 19


@needs_phase5
def test_real_phase5_artifact_is_the_locked_segmentation():
    meta = json.loads(PHASE5.with_name(PHASE5.stem + ".metadata.json").read_text(encoding="utf-8"))
    assert meta["selected_k"] == 3 and meta["random_state"] == 42
    assert tuple(meta["feature_names"]) == LOCKED_SEGMENTATION_FEATURES
    assert meta["training"]["uses_target"] is False and meta["training"]["uses_test"] is False
    assert sha256_file(PHASE5) == meta["artifact_sha256"]
