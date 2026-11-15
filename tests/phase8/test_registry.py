"""Model Registry: registration, metadata, production alias, idempotence, and refusal to promote unverified bytes."""
from __future__ import annotations

from dataclasses import replace
from pathlib import Path
from urllib.parse import unquote, urlparse

import pytest

from mlops import ModelIntegrityError, RegistryError
from mlops._client import get_client
from mlops.integrity import sha256_file
from mlops.registry import fetch_verified_model, register_verified_model, registry_snapshot
from mlops.tracking import log_model_run
from tests.phase8.conftest import LOCKED, METADATA, MODEL

NAME = "TriChurn-Churn-Model"


@pytest.fixture
def registered(settings):
    run = log_model_run(settings)
    return settings, run, register_verified_model(settings, run.run_id), get_client(settings)


def test_the_model_is_registered_under_the_configured_name(registered):
    _, run, result, client = registered
    assert result.model_name == NAME and not result.reused
    assert client.get_registered_model(NAME).name == NAME
    version = client.get_model_version(NAME, result.registry_version)
    assert version.run_id == run.run_id and version.status == "READY"


def test_semantic_version_is_preserved_separately_from_the_registry_number(registered):
    _, _, result, client = registered
    assert result.registry_version == "1" and result.semantic_version == "2.0.0"
    assert client.get_model_version(NAME, "1").tags["model_version"] == "2.0.0"


def test_version_tags(registered):
    _, _, result, client = registered
    tags = client.get_model_version(NAME, result.registry_version).tags
    assert tags == {"project": "TriChurn", "phase": "8", "model_version": "2.0.0", "model_type": "churn_prediction",
                    "status": "production", "artifact_sha256": LOCKED}


def test_production_alias_points_at_the_verified_version(registered):
    _, _, result, client = registered
    assert result.alias == "production"
    assert str(client.get_model_version_by_alias(NAME, "production").version) == result.registry_version


def test_registration_is_idempotent(registered):
    settings, run, first, client = registered
    second = register_verified_model(settings, run.run_id)
    assert second.reused and second.registry_version == first.registry_version
    assert len(client.search_model_versions(f"name='{NAME}'")) == 1


def test_a_tampered_model_is_never_registered(tampered_settings, settings):
    good = log_model_run(settings)                                        # a legitimate run exists
    with pytest.raises(ModelIntegrityError):
        register_verified_model(tampered_settings, good.run_id)
    client = get_client(settings)
    assert client.search_registered_models() == []


def test_a_new_unverified_model_is_not_promoted(settings):
    run = log_model_run(settings)
    with pytest.raises(ModelIntegrityError):
        register_verified_model(replace(settings, model_sha256="b" * 64), run.run_id)
    assert get_client(settings).search_registered_models() == []


def _stored_model(run_id: str, client) -> Path:
    uri = client.get_run(run_id).info.artifact_uri
    artifact_path = unquote(urlparse(uri).path)

    # Windows file URI: /C:/Users/... -> C:/Users/...
    if (
        len(artifact_path) > 2
        and artifact_path.startswith("/")
        and artifact_path[2] == ":"
    ):
        artifact_path = artifact_path[1:]

    return Path(artifact_path) / "model" / MODEL.name


def test_corrupted_stored_artifact_blocks_registration(settings):
    run = log_model_run(settings)
    client = get_client(settings)
    stored = _stored_model(run.run_id, client)
    raw = bytearray(stored.read_bytes())
    raw[10] ^= 0xFF
    stored.write_bytes(bytes(raw))
    with pytest.raises(ModelIntegrityError) as info:
        register_verified_model(settings, run.run_id)
    assert info.value.reason == "sha256_mismatch"
    assert client.search_registered_models() == []


def test_fetch_returns_bytes_identical_to_the_locked_model(registered, tmp_path):
    settings, *_ = registered
    fetched = fetch_verified_model(settings, tmp_path / "dl")
    assert sha256_file(fetched) == LOCKED and fetched.read_bytes() == MODEL.read_bytes()
    assert (fetched.parent / METADATA.name).is_file()


def test_fetch_fails_when_the_registry_copy_was_altered_after_registration(registered, tmp_path):
    settings, run, _, client = registered
    stored = _stored_model(run.run_id, client)
    raw = bytearray(stored.read_bytes())
    raw[20] ^= 0x01
    stored.write_bytes(bytes(raw))
    with pytest.raises(ModelIntegrityError):
        fetch_verified_model(settings, tmp_path / "dl")


def test_fetch_without_a_registered_model_is_a_registry_error(settings, tmp_path):
    with pytest.raises(RegistryError):
        fetch_verified_model(settings, tmp_path / "dl")


def test_snapshot_states(settings, registered):
    assert registry_snapshot(registered[0])["status"] == "registered"
    snap = registry_snapshot(registered[0])
    assert snap["alias"] == "production" and snap["semantic_version"] == "2.0.0" and snap["matches_pinned_sha256"]


def test_snapshot_not_registered(settings):
    log_model_run(settings)
    assert registry_snapshot(settings)["status"] == "not_registered"


def test_snapshot_never_raises_when_mlflow_is_missing(settings, monkeypatch):
    def missing():
        raise RegistryError("mlflow is not installed")
    monkeypatch.setattr("mlops.registry.import_mlflow", missing)
    assert registry_snapshot(settings) == {"status": "mlflow_not_installed", "model_name": NAME}


def test_snapshot_never_raises_when_the_server_is_unreachable(monkeypatch):
    from mlops import MlopsSettings
    monkeypatch.setenv("MLFLOW_HTTP_REQUEST_MAX_RETRIES", "0")
    monkeypatch.setenv("MLFLOW_HTTP_REQUEST_TIMEOUT", "2")
    snap = registry_snapshot(MlopsSettings(tracking_uri="http://127.0.0.1:9", tracking_configured=True))
    assert snap["status"] == "unavailable" and "127.0.0.1" not in str(snap)
