"""Phase 2 - candidate comparison on TRAIN CV + VALIDATION."""
import inspect

import pytest

from ml.pipelines.model_selection import (
    SELECTABLE_METRICS,
    ModelComparison,
    compare_models,
    composite_score,
    validation_metrics,
)
from ml.pipelines.preprocessing import plan_features, prepare_xy
from ml.pipelines.training import MODEL_NAMES, split_raw
from ml.pipelines.tuning import tune_all
from tests.conftest import make_churn_frame


@pytest.fixture(scope="module")
def env(spec, quality_cfg, training_cfg, features_cfg, fast_opt_cfg):
    raw = split_raw(make_churn_frame(1400, seed=6), spec, 0.15, 0.15, 42)
    plan = plan_features(raw.train, spec, quality_cfg)
    Xt, yt, _ = prepare_xy(raw.train, spec, plan)
    Xv, yv, _ = prepare_xy(raw.val, spec, plan)
    tuning = tune_all(Xt, yt, plan, training_cfg, features_cfg, fast_opt_cfg, 42)
    cmp = compare_models(tuning, Xt, yt, Xv, yv, plan, features_cfg, fast_opt_cfg["selection"],
                         fast_opt_cfg["threshold"], 42)
    return dict(plan=plan, Xt=Xt, yt=yt, Xv=Xv, yv=yv, tuning=tuning, cmp=cmp)


def test_composite_score_known_value():
    cv = dict(pr_auc=0.6, roc_auc=0.8, f1=0.5, recall=0.7)
    val = dict(pr_auc=0.4, roc_auc=0.6, f1=0.3, recall=0.5)
    cfg = {"cv_weight": 0.5, "validation_weight": 0.5, "metric_weights": {"pr_auc": 1, "roc_auc": 1}}
    assert composite_score(cv, val, cfg) == pytest.approx(0.5 * 0.7 + 0.5 * 0.5)
    cfg = {"cv_weight": 1, "validation_weight": 0, "metric_weights": {"pr_auc": 3, "f1": 1}}
    assert composite_score(cv, val, cfg) == pytest.approx((3 * 0.6 + 0.5) / 4)   # weights normalised
    with pytest.raises(ValueError, match="Unknown selection metrics"):
        composite_score(cv, val, {**cfg, "metric_weights": {"auc_of_unicorns": 1}})


def test_default_selection_config_is_valid_and_emphasises_requested_metrics(optimization_cfg):
    w = optimization_cfg["selection"]["metric_weights"]
    assert set(w) <= set(SELECTABLE_METRICS) and {"pr_auc", "recall", "f1", "roc_auc"} <= set(w)
    assert max(w, key=w.get) == "pr_auc"


def test_comparison_covers_all_three_models_with_separated_metric_blocks(env):
    cmp: ModelComparison = env["cmp"]
    assert {e.name for e in cmp.evaluations} == set(MODEL_NAMES)
    for e in cmp.evaluations:
        assert set(e.validation) == {"probability_metrics", "threshold_metrics"}
        assert {"roc_auc", "pr_auc", "brier", "log_loss"} <= set(e.validation["probability_metrics"])
        assert {"accuracy", "precision", "recall", "f1", "threshold"} <= set(e.validation["threshold_metrics"])
        assert e.validation["threshold_metrics"]["threshold"] == 0.5
        assert e.baseline_cv is not None and e.baseline_validation is not None
        assert e.pipeline is not None and hasattr(e.pipeline, "predict_proba")


def test_each_model_is_compared_at_its_own_train_derived_threshold(env):
    for e in env["cmp"].evaluations:
        assert 0.05 <= e.selection_threshold <= 0.95
        assert e.cv_at_selection_threshold["threshold"] == e.validation_at_selection_threshold["threshold"] \
            == e.selection_threshold
        assert e.cv_at_selection_threshold["f1"] > 0 and e.validation_at_selection_threshold["f1"] > 0
        # the fixed-0.5 numbers are still reported (information only)
        assert e.validation["threshold_metrics"]["threshold"] == 0.5


def test_class_weighting_no_longer_distorts_threshold_dependent_comparison(spec, quality_cfg, training_cfg,
                                                                           features_cfg, fast_opt_cfg):
    """Principle behind the fix: at 0.5, 'balanced' inflates recall a lot; at each model's own TRAIN-derived
    threshold the two strategies score about the same, so the comparison reflects model quality."""
    from sklearn.base import clone
    from sklearn.model_selection import cross_val_predict

    from ml.pipelines.evaluation import compute_metrics, cv_splitter
    from ml.pipelines.thresholding import optimize_threshold
    from ml.pipelines.tuning import build_candidate_pipeline
    raw = split_raw(make_churn_frame(3000, seed=17, churn_target_rate=0.15), spec, 0.15, 0.15, 42)
    plan = plan_features(raw.train, spec, quality_cfg)
    Xt, yt, _ = prepare_xy(raw.train, spec, plan)
    Xv, yv, _ = prepare_xy(raw.val, spec, plan)
    at_half, at_own = {}, {}
    for imb in ("none", "balanced"):
        pipe = build_candidate_pipeline("logistic_regression", imb, {"C": 1.0, "max_iter": 2000}, yt, plan,
                                        features_cfg, 42)
        oof = cross_val_predict(clone(pipe), Xt, yt, cv=cv_splitter(3, 42), method="predict_proba")[:, 1]
        thr = optimize_threshold(yt, oof, {**fast_opt_cfg["threshold"], "override": None}).threshold
        pipe.fit(Xt, yt)
        p = pipe.predict_proba(Xv)[:, 1]
        at_half[imb] = compute_metrics(yv, p, 0.5)["recall"]
        at_own[imb] = compute_metrics(yv, p, thr)["f1"]
    assert at_half["balanced"] - at_half["none"] > 0.25          # the artifact the old comparison rewarded
    assert abs(at_own["balanced"] - at_own["none"]) < 0.06       # the fair comparison removes it


def test_selected_model_is_argmax_of_composite_and_validation_scores_match_refit(env):
    cmp = env["cmp"]
    assert cmp.selected == max(cmp.evaluations, key=lambda e: e.composite).name
    assert cmp.selected_evaluation.composite == max(e.composite for e in cmp.evaluations)
    ev = cmp.selected_evaluation
    again = validation_metrics(env["yv"], ev.pipeline.predict_proba(env["Xv"])[:, 1])
    assert again == ev.validation
    assert "composite" in cmp.reason and ev.name == cmp.selected


def test_selection_follows_configured_weights(env, fast_opt_cfg, features_cfg):
    """Control: the selection really is driven by the configured metric weights."""
    cfg = {**fast_opt_cfg["selection"], "cv_weight": 0.0, "validation_weight": 1.0, "metric_weights": {"roc_auc": 1}}
    cmp = compare_models(env["tuning"], env["Xt"], env["yt"], env["Xv"], env["yv"], env["plan"], features_cfg,
                         cfg, fast_opt_cfg["threshold"], 42)
    best = max(cmp.evaluations, key=lambda e: e.validation["probability_metrics"]["roc_auc"])
    assert cmp.selected == best.name


def test_comparison_functions_cannot_receive_test_data():
    for fn in (compare_models, composite_score, validation_metrics):
        assert not {n for n in inspect.signature(fn).parameters if "test" in n}
