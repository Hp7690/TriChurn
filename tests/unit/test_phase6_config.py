from __future__ import annotations

from pathlib import Path

import pytest

from app.core.config import (
    DEFAULT_PHASE2_MODEL,
    DEFAULT_PHASE5_MODEL,
    LOCKED_PHASE2_SHA256,
    ConfigurationError,
    Settings,
    default_project_root,
)


def test_defaults_are_production_and_locked():
    s = Settings()
    assert s.environment == "production" and s.enable_docs is True and s.adapter_factory is None
    assert s.phase2_expected_sha256 == LOCKED_PHASE2_SHA256
    assert s.phase2_model_path == DEFAULT_PHASE2_MODEL and s.phase5_model_path == DEFAULT_PHASE5_MODEL
    assert (s.expected_segmentation_k, s.expected_segmentation_seed) == (3, 42)


def test_project_root_is_the_directory_that_contains_app():
    assert (default_project_root() / "app" / "main.py").is_file()


def test_relative_paths_are_anchored_at_the_project_root_not_the_cwd(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    s = Settings(project_root=tmp_path / "proj")
    assert s.resolve("models/x.joblib") == tmp_path / "proj" / "models" / "x.joblib"
    absolute = Path(tmp_path).resolve() / "elsewhere"
    assert s.resolve(absolute) == absolute


def test_from_env_reads_trichurn_variables(tmp_path):
    env = {"TRICHURN_ENVIRONMENT": "development", "TRICHURN_PROJECT_ROOT": str(tmp_path),
           "TRICHURN_PHASE2_MODEL": "m/a.joblib", "TRICHURN_PHASE5_MODEL": "m/b.joblib",
           "TRICHURN_PHASE5_SHA256": "A" * 64, "TRICHURN_ENABLE_DOCS": "false",
           "TRICHURN_DATASET_CSV": "d.csv", "TRICHURN_ADAPTER_FACTORY": "pkg.mod:build"}
    s = Settings.from_env(env)
    assert (s.environment, s.project_root, s.phase2_model_path, s.phase5_model_path) == (
        "development", tmp_path, "m/a.joblib", "m/b.joblib")
    assert s.phase5_expected_sha256 == "a" * 64 and s.enable_docs is False
    assert s.dataset_csv_path == "d.csv" and s.adapter_factory == "pkg.mod:build"
    assert Settings.from_env({}).phase2_expected_sha256 == LOCKED_PHASE2_SHA256


def test_pinning_can_only_be_disabled_explicitly():
    assert Settings.from_env({"TRICHURN_PHASE2_SHA256": "disabled"}).phase2_expected_sha256 is None
    for bad in ("", "abc", "g" * 64, "a" * 63):
        with pytest.raises(ConfigurationError, match="SHA-256"):
            Settings.from_env({"TRICHURN_PHASE2_SHA256": bad})


@pytest.mark.parametrize("bad", ["False", "no", "0", "1", "", "TRUE"])
def test_booleans_must_be_exactly_true_or_false(bad):
    with pytest.raises(ConfigurationError, match="'true' or 'false'"):
        Settings.from_env({"TRICHURN_ENABLE_DOCS": bad})


def test_unknown_environment_is_rejected_without_echoing_the_value():
    with pytest.raises(ConfigurationError) as exc:
        Settings(environment="prod-secret-xyz")
    assert "prod-secret-xyz" not in str(exc.value)
