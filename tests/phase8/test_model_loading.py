"""Model loading: verify FIRST, deserialise only afterwards; correct model loads; anything else fails safely."""
from __future__ import annotations

import sys
from dataclasses import replace

import pandas as pd
import pytest

from app.schemas.common import CustomerRequest
from mlops import MlopsConfigurationError, MlopsSettings, ModelIntegrityError
from mlops.loading import load_verified_model
from tests.phase8.conftest import LOCKED, MODEL, ROOT

FEATURES = CustomerRequest.model_config["json_schema_extra"]["example"]["features"]


@pytest.fixture
def no_unpickling(monkeypatch):
    """Fail the test if the (unpickling) Phase 3 loader is ever reached."""
    def boom(*args, **kwargs):
        raise AssertionError("the artifact was deserialised although verification had failed")
    monkeypatch.setattr("ml.explainability.load_verified_artifact", boom)


def test_correct_model_loads_with_the_locked_threshold_and_metadata():
    loaded = load_verified_model(MlopsSettings())
    assert loaded.sha256 == LOCKED
    assert loaded.artifact.threshold == 0.34 and loaded.sidecar["model_version"] == "2.0.0"


def test_loaded_model_predictions_are_deterministic_and_equal_the_existing_loader():
    from ml.explainability import load_verified_artifact
    frame = pd.DataFrame([FEATURES])
    a = load_verified_model(MlopsSettings()).artifact.predict_proba(frame)
    b = load_verified_model(MlopsSettings()).artifact.predict_proba(frame)
    direct = load_verified_artifact(MODEL).artifact.predict_proba(frame)
    assert list(a) == list(b) == list(direct) and 0.0 <= float(a[0]) <= 1.0


def test_wrong_pin_is_refused_before_unpickling(no_unpickling):
    with pytest.raises(ModelIntegrityError) as info:
        load_verified_model(replace(MlopsSettings(), model_sha256="c" * 64))
    assert info.value.reason == "sha256_mismatch"


def test_a_tampered_file_is_refused_before_unpickling(tampered_settings, no_unpickling):
    with pytest.raises(ModelIntegrityError) as info:
        load_verified_model(tampered_settings)
    assert info.value.reason == "sha256_mismatch"


def test_a_missing_artifact_is_handled_safely_without_leaking_the_path(tmp_path, no_unpickling):
    settings = MlopsSettings(project_root=tmp_path)
    with pytest.raises(ModelIntegrityError) as info:
        load_verified_model(settings)
    assert info.value.reason == "missing" and str(tmp_path) not in str(info.value)


def test_a_missing_sidecar_is_refused(tmp_path, no_unpickling):
    (tmp_path / "models").mkdir()
    (tmp_path / "models" / MODEL.name).write_bytes(MODEL.read_bytes())
    with pytest.raises(ModelIntegrityError) as info:
        load_verified_model(MlopsSettings(project_root=tmp_path))
    assert info.value.reason == "metadata_unreadable"


def test_a_version_mismatch_is_refused(no_unpickling):
    with pytest.raises(ModelIntegrityError) as info:
        load_verified_model(replace(MlopsSettings(), model_version="9.9.9"))
    assert info.value.reason == "version_mismatch"


def test_loading_works_without_mlflow_installed(monkeypatch):
    monkeypatch.setitem(sys.modules, "mlflow", None)               # any `import mlflow` now raises ImportError
    assert load_verified_model(MlopsSettings()).artifact.threshold == 0.34


def test_loading_works_offline_even_if_the_configured_tracking_server_is_unreachable():
    settings = MlopsSettings(tracking_uri="http://127.0.0.1:9", tracking_configured=True)
    assert load_verified_model(settings).artifact.threshold == 0.34      # the loader never contacts MLflow


# --------------------------------------------------------------------------------------------- configuration
def test_defaults_are_the_locked_values():
    s = MlopsSettings.from_env({})
    assert (s.experiment_name, s.model_name, s.model_version) == (
        "TriChurn-Churn-Prediction", "TriChurn-Churn-Model", "2.0.0")
    assert s.model_sha256 == LOCKED and s.model_file == ROOT / "models" / MODEL.name and not s.tracking_configured
    assert s.effective_tracking_uri.startswith("sqlite:///") and s.effective_artifact_location.startswith("file:///")


def test_environment_overrides_are_applied():
    s = MlopsSettings.from_env({"MLFLOW_TRACKING_URI": "http://mlflow.example:5000", "MLFLOW_EXPERIMENT_NAME": "Exp",
                                "MLFLOW_MODEL_NAME": "M", "MLFLOW_MODEL_VERSION": "3.1.4",
                                "TRICHURN_MODEL_PATH": "models/other.joblib", "TRICHURN_MODEL_SHA256": "A" * 64})
    assert s.effective_tracking_uri == "http://mlflow.example:5000" and s.tracking_configured
    assert (s.experiment_name, s.model_name, s.model_version) == ("Exp", "M", "3.1.4")
    assert s.model_sha256 == "a" * 64 and s.model_file == ROOT / "models" / "other.joblib"


@pytest.mark.parametrize("env", [{"TRICHURN_MODEL_SHA256": "xyz"}, {"TRICHURN_MODEL_SHA256": "disabled"},
                                 {"MLFLOW_MODEL_VERSION": "two"}, {"MLFLOW_MODEL_NAME": "bad/name"},
                                 {"MLFLOW_EXPERIMENT_NAME": ""}])
def test_malformed_configuration_is_rejected_without_echoing_the_value(env):
    if "MLFLOW_EXPERIMENT_NAME" in env:
        env = {"MLFLOW_EXPERIMENT_NAME": "   "}
        with pytest.raises(MlopsConfigurationError):
            MlopsSettings.from_env(env)
        return
    with pytest.raises(MlopsConfigurationError) as info:
        MlopsSettings.from_env(env)
    assert next(iter(env.values())) not in str(info.value)


def test_relative_paths_are_anchored_at_the_project_root_not_the_cwd(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    assert MlopsSettings().model_file == ROOT / "models" / MODEL.name
    assert MlopsSettings(model_path=str(tmp_path / "x.joblib")).model_file == tmp_path / "x.joblib"
