"""Integrity verification: correct digest passes, anything else fails safely (no path leakage, no side effects)."""
from __future__ import annotations

import hashlib
import json
import shutil

import pytest

from mlops import ModelIntegrityError, require_verified, sha256_file, verify_model_artifact
from tests.phase8.conftest import LOCKED, METADATA, MODEL, file_state


def test_correct_sha_passes_and_reports_both_digests():
    report = verify_model_artifact(MODEL, LOCKED, metadata_path=METADATA, expected_version="2.0.0")
    assert report.ok and report.reason is None
    assert report.expected_sha256 == report.actual_sha256 == LOCKED
    assert report.actual_version == "2.0.0" and report.artifact == MODEL.name


def test_streamed_digest_equals_hashlib():
    assert sha256_file(MODEL) == hashlib.sha256(MODEL.read_bytes()).hexdigest() == LOCKED


def test_wrong_sha_fails_safely_with_both_digests_reported():
    wrong = "0" * 64
    report = verify_model_artifact(MODEL, wrong)
    assert not report.ok and report.reason == "sha256_mismatch"
    assert report.expected_sha256 == wrong and report.actual_sha256 == LOCKED


def test_expected_digest_is_case_insensitive():
    assert verify_model_artifact(MODEL, LOCKED.upper()).ok


@pytest.mark.parametrize("bad", ["", "abc", "g" * 64, "0" * 63, "0" * 65])
def test_malformed_expected_digest_is_rejected(bad):
    report = verify_model_artifact(MODEL, bad)
    assert not report.ok and report.reason == "invalid_expected_sha256" and report.actual_sha256 is None


def test_single_flipped_byte_is_detected(tampered_settings):
    report = verify_model_artifact(tampered_settings.model_file, LOCKED)
    assert not report.ok and report.reason == "sha256_mismatch" and report.actual_sha256 != LOCKED


def test_missing_artifact(tmp_path):
    report = verify_model_artifact(tmp_path / "nope.joblib", LOCKED)
    assert not report.ok and report.reason == "missing" and report.actual_sha256 is None


def test_directory_instead_of_file_is_missing(tmp_path):
    assert verify_model_artifact(tmp_path, LOCKED).reason == "missing"


def test_version_mismatch_is_detected():
    report = verify_model_artifact(MODEL, LOCKED, metadata_path=METADATA, expected_version="9.9.9")
    assert not report.ok and report.reason == "version_mismatch" and report.actual_version == "2.0.0"


def test_sidecar_digest_must_agree_with_the_file(tmp_path):
    forged = tmp_path / METADATA.name
    meta = json.loads(METADATA.read_text())
    meta["artifact_sha256"] = "1" * 64
    forged.write_text(json.dumps(meta))
    report = verify_model_artifact(MODEL, LOCKED, metadata_path=forged)
    assert not report.ok and report.reason == "metadata_sha256_mismatch"


def test_unreadable_sidecar(tmp_path):
    broken = tmp_path / "meta.json"
    broken.write_text("{not json")
    assert verify_model_artifact(MODEL, LOCKED, metadata_path=broken).reason == "metadata_unreadable"
    assert verify_model_artifact(MODEL, LOCKED, metadata_path=tmp_path / "absent.json").reason == "metadata_unreadable"


def test_require_verified_raises_with_name_and_reason_only(tmp_path):
    with pytest.raises(ModelIntegrityError) as info:
        require_verified(tmp_path / "secret_dir" / "m.joblib", LOCKED)
    assert info.value.reason == "missing" and info.value.artifact == "m.joblib"
    assert "secret_dir" not in str(info.value) and str(tmp_path) not in str(info.value)


def test_require_verified_returns_the_report_when_ok():
    assert require_verified(MODEL, LOCKED, metadata_path=METADATA, expected_version="2.0.0").ok


def test_verification_never_modifies_the_artifact(tmp_path):
    copy = tmp_path / MODEL.name
    shutil.copy(MODEL, copy)
    before = file_state(copy)
    verify_model_artifact(copy, "0" * 64)
    verify_model_artifact(copy, LOCKED)
    assert file_state(copy) == before
