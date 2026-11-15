import numpy as np
import pytest

from ml.pipelines.evaluation import METRIC_NAMES, compute_metrics, cross_validate_pipeline
from ml.pipelines.preprocessing import build_pipeline, plan_features, prepare_xy
from ml.pipelines.training import (
    MODEL_NAMES,
    make_estimator,
    run_training,
    split_data,
    train_models,
)
from tests.conftest import make_churn_frame


def test_compute_metrics_known_values():
    y = np.array([1, 1, 0, 0, 0, 0])
    p = np.array([0.9, 0.4, 0.6, 0.2, 0.1, 0.3])
    m = compute_metrics(y, p)
    assert m["confusion_matrix"] == [[3, 1], [1, 1]]
    assert m["accuracy"] == pytest.approx(4 / 6)
    assert m["precision"] == pytest.approx(0.5) and m["recall"] == pytest.approx(0.5)
    assert m["f1"] == pytest.approx(0.5)
    assert m["roc_auc"] == pytest.approx(7 / 8)  # 7 of 8 pos/neg pairs ranked correctly
    assert 0 < m["pr_auc"] <= 1


def test_compute_metrics_all_negative_predictions_does_not_crash():
    m = compute_metrics([1, 0, 0, 1], [0.1, 0.2, 0.1, 0.3])
    assert m["precision"] == 0.0 and m["recall"] == 0.0 and m["f1"] == 0.0


def test_make_estimator_imbalance_settings(training_cfg):
    import pandas as pd
    y = pd.Series([0] * 90 + [1] * 10)
    xgb = make_estimator("xgboost", "balanced", y, training_cfg, 1)
    assert xgb.scale_pos_weight == pytest.approx(9.0)
    assert make_estimator("xgboost", "none", y, training_cfg, 1).scale_pos_weight == 1.0
    assert make_estimator("logistic_regression", "balanced", y, training_cfg, 1).class_weight == "balanced"
    assert make_estimator("random_forest", "none", y, training_cfg, 1).class_weight is None
    with pytest.raises(ValueError):
        make_estimator("nope", "none", y, training_cfg, 1)


def test_cross_validation_reports_mean_and_std(df, spec, quality_cfg, training_cfg, features_cfg):
    plan = plan_features(df, spec, quality_cfg)
    X, y, _ = prepare_xy(df, spec, plan)
    pipe = build_pipeline(plan, make_estimator("logistic_regression", "balanced", y, training_cfg, 1),
                          features_cfg)
    cv = cross_validate_pipeline(pipe, X, y, n_splits=4, seed=1)
    assert cv["n_splits"] == 4
    for m in METRIC_NAMES:
        assert 0 <= cv[m]["mean"] <= 1 and cv[m]["std"] >= 0
    assert cv["roc_auc"]["mean"] > 0.65  # synthetic data has real signal


def test_run_training_end_to_end_all_models(df, spec, quality_cfg, training_cfg, features_cfg):
    cfg = {**training_cfg, "cv": {"n_splits": 3}}
    rep = run_training(df, spec, quality_cfg, cfg, features_cfg)
    d = rep.to_dict()
    assert {r["name"] for r in d["results"]} == set(MODEL_NAMES)
    assert len(d["results"]) == 6  # 3 models x {none, balanced}
    for name in MODEL_NAMES:
        picked = [r for r in d["results"] if r["name"] == name and r["selected_imbalance"]]
        assert len(picked) == 1
        for r in (x for x in d["results"] if x["name"] == name):
            assert 0.6 < r["validation"]["roc_auc"] <= 1.0
            assert r["cv"]["pr_auc"]["std"] >= 0
    assert sum(d["split_sizes"].values()) == len(df)
    assert d["quality"]["band"] in {"Excellent", "Good", "Needs Attention", "Poor"}
    import json
    json.dumps(d)  # fully serialisable


def test_balanced_weights_raise_recall_under_imbalance(spec, quality_cfg, training_cfg, features_cfg):
    d = make_churn_frame(2500, seed=11, churn_target_rate=0.08)
    plan = plan_features(d, spec, quality_cfg)
    X, y, _ = prepare_xy(d, spec, plan)
    s = split_data(X, y, 0.15, 0.15, 42)
    cfg = {**training_cfg, "cv": {"n_splits": 3}}
    res = train_models(s.X_train, s.y_train, s.X_val, s.y_val, plan, cfg, features_cfg,
                       models=["logistic_regression"])
    by = {r.imbalance: r for r in res}
    assert by["balanced"].validation["recall"] > by["none"].validation["recall"]


def test_training_is_reproducible(df, spec, quality_cfg, training_cfg, features_cfg):
    cfg = {**training_cfg, "cv": {"n_splits": 3}}
    a = run_training(df, spec, quality_cfg, cfg, features_cfg, models=["logistic_regression"])
    b = run_training(df, spec, quality_cfg, cfg, features_cfg, models=["logistic_regression"])
    assert a.to_dict()["results"][0]["validation"] == b.to_dict()["results"][0]["validation"]


def test_extreme_imbalance_still_trains_or_fails_clearly(spec, quality_cfg, training_cfg, features_cfg):
    from ml.errors import ValidationError
    d = make_churn_frame(1500, seed=5)
    d["Churn"] = "No"
    d.loc[d.sample(n=25, random_state=0).index, "Churn"] = "Yes"  # ~1.7% positives
    cfg = {**training_cfg, "cv": {"n_splits": 3}}
    rep = run_training(d, spec, quality_cfg, cfg, features_cfg, models=["logistic_regression"])
    assert rep.quality["components"]["imbalance"] > 0
    d.loc[d.index[:], "Churn"] = "No"
    d.loc[d.index[:3], "Churn"] = "Yes"
    with pytest.raises(ValidationError, match="TOO_FEW_MINORITY_SAMPLES"):
        run_training(d, spec, quality_cfg, cfg, features_cfg)
