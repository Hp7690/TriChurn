"""MLflow tracking of the EXISTING model: experiment, run, metrics, params, artifact - and its guard rails."""
from __future__ import annotations

import json
import math
import shutil
from pathlib import Path

import pytest

from mlops import MlopsSettings, ModelIntegrityError, RegistryError
from mlops._client import get_client
from mlops.integrity import sha256_file
from mlops.tracking import extract_metrics, extract_params, log_model_run
from tests.phase8.conftest import LOCKED, METADATA, MODEL, ROOT, SPEC_METRICS, file_state, store_settings

EXPECTED_PARAM_KEYS = {
    "registered_model_name", "model_name", "model_version", "threshold", "threshold_metric", "threshold_source",
    "random_state", "feature_count", "model_feature_count", "target", "positive_class", "imbalance_strategy",
    "calibration_method", "dataset_version", "dataset_rows", "split_train", "split_validation", "split_test"}


@pytest.fixture
def tracked(settings):
    result = log_model_run(settings)
    client = get_client(settings)
    return settings, result, client, client.get_run(result.run_id)


def test_experiment_is_created_with_the_configured_name_and_explicit_artifact_location(tracked):
    settings, result, client, _ = tracked
    exp = client.get_experiment_by_name("TriChurn-Churn-Prediction")
    assert exp is not None and exp.experiment_id == result.experiment_id
    assert exp.artifact_location == settings.effective_artifact_location          # never an implicit ./mlruns


def test_run_is_finished_and_carries_the_required_tags(tracked):
    _, result, _, run = tracked
    assert run.info.status == "FINISHED" and not result.reused
    for key, value in {"project": "TriChurn", "phase": "8", "model_version": "2.0.0",
                       "model_type": "churn_prediction", "status": "production", "artifact_sha256": LOCKED,
                       "metrics_split": "test", "integrity_verified_before": "true",
                       "integrity_verified_after": "true"}.items():
        assert run.data.tags[key] == value, key


def test_all_eight_metrics_are_logged_with_the_stored_values(tracked):
    _, _, _, run = tracked
    stored = json.loads(METADATA.read_text())["metrics"]["test"]
    expected = {**stored["probability_metrics"], **stored["threshold_metrics"]}
    expected["brier_score"] = expected.pop("brier")
    logged = run.data.metrics
    assert set(SPEC_METRICS) <= set(logged)
    for name in SPEC_METRICS:
        assert logged[name] == pytest.approx(expected[name], abs=0, rel=0) or logged[name] == expected[name]


def test_logged_metrics_equal_the_specification_baseline_to_four_decimals(tracked):
    _, _, _, run = tracked
    for name, value in SPEC_METRICS.items():
        assert round(run.data.metrics[name], 4) == value, name


def test_params_are_recovered_from_the_artifact_metadata(tracked):
    _, _, _, run = tracked
    p = run.data.params
    assert p["model_version"] == "2.0.0" and p["threshold"] == "0.34" and p["random_state"] == "42"
    assert p["feature_count"] == "19" and p["model_feature_count"] == "58" and p["model_name"] == "logistic_regression"
    assert p["dataset_version"] == "sha256:16320c9c1ec7" and p["dataset_rows"] == "7043"
    assert (p["hp_solver"], p["hp_C"], p["hp_max_iter"]) == ("lbfgs", "3.0", "3000")


def test_no_training_information_is_invented(tracked):
    _, _, _, run = tracked
    keys = set(run.data.params)
    assert EXPECTED_PARAM_KEYS <= keys
    extra = {k for k in keys if not k.startswith(("hp_", "train_env_"))} - EXPECTED_PARAM_KEYS
    assert not extra, extra
    assert not keys & {"learning_rate", "n_estimators", "max_depth", "epochs", "batch_size"}


def test_the_artifact_is_logged_and_the_stored_copy_is_byte_identical(tracked, tmp_path):
    _, result, client, _ = tracked
    names = {a.path for a in client.list_artifacts(result.run_id, "model")}
    assert names == {f"model/{MODEL.name}", f"model/{METADATA.name}"}
    stored = client.download_artifacts(result.run_id, f"model/{MODEL.name}", str(tmp_path))
    assert sha256_file(Path(stored)) == LOCKED


def test_the_original_model_file_is_not_modified_or_replaced(settings):
    before = file_state(MODEL)
    log_model_run(settings)
    log_model_run(settings, force=True)
    assert file_state(MODEL) == before and sha256_file(MODEL) == LOCKED


def test_tracking_is_idempotent_for_the_same_digest(settings):
    first = log_model_run(settings)
    second = log_model_run(settings)
    assert second.reused and second.run_id == first.run_id
    client = get_client(settings)
    assert len(client.search_runs([first.experiment_id])) == 1


def test_force_logs_an_additional_run(settings):
    first = log_model_run(settings)
    second = log_model_run(settings, force=True)
    assert not second.reused and second.run_id != first.run_id
    assert len(get_client(settings).search_runs([first.experiment_id])) == 2


def test_a_digest_mismatch_is_refused_before_any_run_exists(tampered_settings):
    with pytest.raises(ModelIntegrityError) as info:
        log_model_run(tampered_settings)
    assert info.value.reason == "sha256_mismatch"
    assert get_client(tampered_settings).get_experiment_by_name("TriChurn-Churn-Prediction") is None


def test_a_wrong_pin_is_refused(tmp_path):
    other = store_settings(tmp_path / "s", model_sha256="a" * 64)
    with pytest.raises(ModelIntegrityError):
        log_model_run(other)


def test_missing_metrics_are_reported_not_fabricated(tmp_path, settings):
    model_dir = tmp_path / "m"
    model_dir.mkdir()
    shutil.copy(MODEL, model_dir / MODEL.name)
    meta = json.loads(METADATA.read_text())
    del meta["metrics"]["test"]
    (model_dir / METADATA.name).write_text(json.dumps(meta))
    broken = store_settings(tmp_path / "s2", model_path=str(model_dir / MODEL.name))
    with pytest.raises(RegistryError, match="metrics"):
        log_model_run(broken)
    assert get_client(broken).get_experiment_by_name("TriChurn-Churn-Prediction") is None


@pytest.mark.parametrize("bad", [float("nan"), float("inf"), "0.8", None, True])
def test_non_finite_or_non_numeric_metrics_are_rejected(bad):
    meta = json.loads(METADATA.read_text())
    meta["metrics"]["test"]["probability_metrics"]["roc_auc"] = bad
    with pytest.raises(RegistryError):
        extract_metrics(meta)


def test_extract_metrics_values_are_finite_floats():
    metrics = extract_metrics(json.loads(METADATA.read_text()))
    assert set(metrics) == set(SPEC_METRICS) and all(math.isfinite(v) for v in metrics.values())


def test_absent_facts_are_omitted_rather_than_defaulted():
    params = extract_params({"model_version": "2.0.0"}, MlopsSettings())
    assert params == {"registered_model_name": "TriChurn-Churn-Model", "model_version": "2.0.0"}


def test_an_unreachable_server_becomes_a_registry_error_and_leaves_the_model_alone(tmp_path, monkeypatch):
    monkeypatch.setenv("MLFLOW_HTTP_REQUEST_MAX_RETRIES", "0")           # fail fast: nothing listens on port 9
    monkeypatch.setenv("MLFLOW_HTTP_REQUEST_TIMEOUT", "2")
    before = file_state(MODEL)
    unreachable = MlopsSettings(tracking_uri="http://127.0.0.1:9", project_root=ROOT, tracking_configured=True)
    with pytest.raises(RegistryError) as info:
        log_model_run(unreachable)
    assert str(tmp_path) not in str(info.value) and "127.0.0.1" not in str(info.value)
    assert file_state(MODEL) == before


def test_no_mlruns_directory_is_created_in_the_project(settings):
    existed = (ROOT / "mlruns").exists()
    log_model_run(settings)
    assert (ROOT / "mlruns").exists() == existed
