"""Phase 2 - the lock, the single final TEST evaluation, serialization and reproducibility."""
import ast
import json
from pathlib import Path

import numpy as np
import pytest

from ml.config import ROOT
from ml.errors import TestSetAlreadyEvaluatedError
from ml.pipelines.evaluation import compute_metrics, probability_metrics
from ml.pipelines.final_evaluation import evaluate_on_test
from ml.pipelines.optimization import (
    resolve_seed,
    run_optimization,
    run_optimization_decisions,
    run_optimization_on_splits,
)
from ml.pipelines.preprocessing import prepare_xy
from ml.pipelines.serialization import load_artifact, resolve_dir
from ml.pipelines.training import split_raw
from tests.conftest import make_churn_frame

MODELS = ["logistic_regression", "xgboost"]


@pytest.fixture(scope="module")
def splits(spec):
    raw = split_raw(make_churn_frame(1500, seed=21), spec, 0.15, 0.15, 42)
    return raw.train.copy(), raw.val.copy(), raw.test.copy()


@pytest.fixture(scope="module")
def decisions(splits, spec, quality_cfg, training_cfg, features_cfg, fast_opt_cfg):
    tr, va, _ = splits
    return run_optimization_decisions(tr, va, spec, quality_cfg, training_cfg, features_cfg, fast_opt_cfg, MODELS)


def test_lock_contains_every_decision_before_test_is_touched(decisions):
    lk = decisions.locked
    assert not lk.test_consumed
    assert lk.model_name == decisions.comparison.selected
    assert lk.calibration_method == decisions.calibration.method
    assert lk.threshold is decisions.threshold and len(lk.fingerprint) == 64
    assert lk.current_fingerprint() == lk.fingerprint


def test_final_evaluation_reports_separate_probability_and_threshold_metrics(decisions, splits, spec):
    import copy
    lk = copy.copy(decisions.locked)            # shallow copy: keep module fixture reusable
    _, _, te = splits
    X, y, _ = prepare_xy(te, spec, lk.plan)
    fin = evaluate_on_test(lk, te, spec)
    p = lk.model.predict_proba(X)[:, 1]
    assert fin.probability_metrics == probability_metrics(y, p)
    assert set(fin.probability_metrics) == {"roc_auc", "pr_auc", "brier", "log_loss"}
    cm = compute_metrics(y, p, lk.threshold.threshold)
    for k in ("accuracy", "precision", "recall", "f1", "confusion_matrix", "threshold"):
        assert fin.threshold_metrics[k] == cm[k]
    assert "roc_auc" not in fin.threshold_metrics and fin.threshold == lk.threshold.threshold
    assert fin.n_test == len(te) and fin.lock_fingerprint == lk.fingerprint
    assert lk.test_consumed is True
    d = fin.to_dict()
    assert d["selected_threshold"] == lk.threshold.threshold
    json.dumps(d)


def test_test_split_can_be_evaluated_only_once(decisions, splits, spec):
    import copy
    lk = copy.copy(decisions.locked)
    lk.test_consumed = False
    _, _, te = splits
    evaluate_on_test(lk, te, spec)
    with pytest.raises(TestSetAlreadyEvaluatedError):
        evaluate_on_test(lk, te, spec)


def test_tampered_lock_refuses_to_read_the_test_split(decisions, splits, spec):
    import copy
    lk = copy.copy(decisions.locked)
    lk.test_consumed = False
    lk.threshold = type(lk.threshold)(**{**lk.threshold.__dict__, "threshold": 0.99})   # change a locked decision
    with pytest.raises(RuntimeError, match="Locked decisions changed"):
        evaluate_on_test(lk, splits[2], spec)
    assert lk.test_consumed is False            # nothing was read


def test_artifact_roundtrip_metadata_and_no_machine_paths(splits, spec, quality_cfg, training_cfg, features_cfg,
                                                          fast_opt_cfg, tmp_path):
    tr, va, te = splits
    rep = run_optimization_on_splits(
        tr, va, te, spec, quality_cfg, training_cfg, features_cfg, fast_opt_cfg,
        dataset_info={"path": "ml/data/raw/x.csv", "version": "sha256:abc"}, models=MODELS,
        artifact_dir=tmp_path, trained_at="2026-01-01T00:00:00+00:00")
    art = rep.artifact
    assert art.model.exists() and art.metadata.exists()
    assert art.model.name == "trichurn_churn_model_v2.0.0.joblib"

    meta = json.loads(art.metadata.read_text())
    required = {"model_name", "model_version", "trained_at", "feature_names", "feature_count",
                "model_feature_names", "model_feature_count", "calibration", "threshold",
                "training_configuration", "random_state", "metrics", "dataset", "hyperparameters",
                "decision_fingerprint", "artifact_sha256", "environment"}
    assert required <= set(meta)
    assert meta["model_name"] == rep.decisions.locked.model_name and meta["trained_at"].startswith("2026-01-01")
    assert meta["feature_count"] == len(meta["feature_names"]) > 5
    assert meta["model_feature_count"] == len(meta["model_feature_names"]) >= meta["feature_count"]
    assert meta["calibration"]["method"] == rep.decisions.calibration.method
    assert meta["threshold"]["value"] == rep.decisions.threshold.threshold
    assert meta["random_state"] == 42 and meta["dataset"]["split_sizes"]["test"] == len(te)
    assert {"cv_train", "validation", "test"} == set(meta["metrics"])
    assert meta["metrics"]["test"]["selected_threshold"] == rep.final.threshold
    assert meta["artifact_sha256"] == art.sha256
    text = art.metadata.read_text()
    assert str(tmp_path) not in text and str(ROOT) not in text          # no machine-specific paths

    loaded = load_artifact(art.model)
    X_raw = te.drop(columns=["Churn"]).head(40)                         # raw customer records
    assert np.allclose(loaded.predict_proba(X_raw), rep.decisions.locked.model.predict_proba(X_raw)[:, 1])
    assert loaded.threshold == rep.decisions.threshold.threshold
    assert np.array_equal(loaded.predict(X_raw), (loaded.predict_proba(X_raw) >= loaded.threshold).astype(int))
    assert loaded.metadata["model_version"] == "2.0.0"


def test_artifact_dir_is_relative_to_project_root_not_cwd(optimization_cfg):
    assert not Path(optimization_cfg["artifacts"]["dir"]).is_absolute()
    assert resolve_dir(optimization_cfg["artifacts"]["dir"]) == ROOT / optimization_cfg["artifacts"]["dir"]
    assert resolve_dir("/abs/place") == Path("/abs/place").absolute()


def test_phase2_is_reproducible_end_to_end(spec, quality_cfg, training_cfg, features_cfg, fast_opt_cfg):
    df = make_churn_frame(1300, seed=31)
    a = run_optimization(df, spec, quality_cfg, training_cfg, features_cfg, fast_opt_cfg, models=MODELS)
    b = run_optimization(df, spec, quality_cfg, training_cfg, features_cfg, fast_opt_cfg, models=MODELS)
    assert a.decisions.locked.fingerprint == b.decisions.locked.fingerprint
    assert a.final.to_dict() == b.final.to_dict()
    assert a.decisions.threshold.to_dict() == b.decisions.threshold.to_dict()
    assert a.decisions.calibration.parameters == b.decisions.calibration.parameters
    assert [e.composite for e in a.decisions.comparison.evaluations] == [e.composite for e in
                                                                         b.decisions.comparison.evaluations]
    json.dumps(a.to_dict(), default=str)


def test_seed_resolution_inherits_training_seed(training_cfg, optimization_cfg):
    assert optimization_cfg["seed"] is None and resolve_seed(training_cfg, optimization_cfg) == training_cfg["seed"]
    assert resolve_seed(training_cfg, {**optimization_cfg, "seed": 7}) == 7


def test_ml_package_stays_pure():
    """frontend -> API -> services -> ML: the ML package must not import web/DB/frontend code."""
    banned = {"fastapi", "starlette", "uvicorn", "sqlalchemy", "psycopg2", "flask", "django", "streamlit",
              "mlflow", "dvc", "airflow", "shap", "requests", "httpx"}
    for path in (ROOT / "ml").rglob("*.py"):
        # Phase 3: `shap` is allowed only inside ml/explainability; it stays banned everywhere else.
        banned_here = banned - {"shap"} if "explainability" in path.relative_to(ROOT / "ml").parts else banned
        for node in ast.walk(ast.parse(path.read_text())):
            names = []
            if isinstance(node, ast.Import):
                names = [a.name for a in node.names]
            elif isinstance(node, ast.ImportFrom) and node.module:
                names = [node.module]
            assert not {n.split(".")[0] for n in names} & banned_here, (path, names)
