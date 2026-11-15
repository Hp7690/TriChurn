"""Phase 2 - hyperparameter tuning (TRAIN only, stratified CV, seeded, reproducible)."""
import inspect

import pytest

from ml.pipelines import tuning
from ml.pipelines.preprocessing import plan_features, prepare_xy
from ml.pipelines.training import MODEL_NAMES, split_raw
from ml.pipelines.tuning import (
    baseline_configs,
    build_candidate_pipeline,
    grid_size,
    sample_configs,
    tune_all,
    tune_model,
)
from tests.conftest import make_churn_frame

REQUIRED_SPACE = {
    "logistic_regression": {"C", "imbalance", "solver"},   # imbalance == class_weight switch
    "random_forest": {"n_estimators", "max_depth", "min_samples_split", "min_samples_leaf", "max_features",
                      "imbalance"},
    "xgboost": {"n_estimators", "max_depth", "learning_rate", "subsample", "colsample_bytree",
                "min_child_weight", "reg_alpha", "reg_lambda", "imbalance"},
}


@pytest.fixture(scope="module")
def xy(spec, quality_cfg):
    raw = split_raw(make_churn_frame(1200, seed=4), spec, 0.15, 0.15, 42)
    plan = plan_features(raw.train, spec, quality_cfg)
    X, y, _ = prepare_xy(raw.train, spec, plan)
    return plan, X, y


def test_search_spaces_cover_every_requested_hyperparameter(optimization_cfg):
    spaces = optimization_cfg["tuning"]["spaces"]
    for model, required in REQUIRED_SPACE.items():
        assert required <= set(spaces[model]), model
        assert all(len(v) >= 1 for v in spaces[model].values())
    sizes = {m: grid_size(spaces[m]) for m in MODEL_NAMES}
    assert all(sizes[m] >= optimization_cfg["tuning"]["n_iter"][m] for m in MODEL_NAMES)  # a real *search*


def test_search_budget_is_practical(optimization_cfg):
    t = optimization_cfg["tuning"]
    folds = t["cv"]["n_splits"]
    fits = sum(n + 2 for n in t["n_iter"].values()) * folds   # +2 baseline candidates per model
    assert fits <= 400, fits
    assert folds >= 3


def test_sampling_is_seeded_unique_and_capped():
    space = {"a": [1, 2, 3], "b": ["x", "y"], "c": [None, 5]}
    assert sample_configs(space, 5, 7) == sample_configs(space, 5, 7)
    assert sample_configs(space, 5, 7) != sample_configs(space, 5, 8)
    got = sample_configs(space, 5, 7)
    assert len({tuple(sorted(c.items(), key=str)) for c in got}) == 5          # no repeats
    assert len(sample_configs(space, 999, 7)) == grid_size(space) == 12        # capped at the grid


def test_baseline_configs_are_phase1_defaults(training_cfg, fast_opt_cfg):
    cfgs = baseline_configs("logistic_regression", training_cfg, fast_opt_cfg)
    assert [c["imbalance"] for c in cfgs] == training_cfg["imbalance"]["candidates"]
    assert all(c["C"] == training_cfg["models"]["logistic_regression"]["C"] for c in cfgs)


def test_imbalance_switch_maps_to_class_weight(xy, features_cfg):
    plan, X, y = xy
    lr = build_candidate_pipeline("logistic_regression", "balanced", {"C": 1.0, "solver": "lbfgs",
                                                                       "max_iter": 500}, y, plan, features_cfg, 1)
    assert lr.named_steps["model"].class_weight == "balanced"
    rf = build_candidate_pipeline("random_forest", "none", {"n_estimators": 10}, y, plan, features_cfg, 1)
    assert rf.named_steps["model"].class_weight is None
    xgb = build_candidate_pipeline("xgboost", "balanced", {"n_estimators": 10}, y, plan, features_cfg, 1)
    assert xgb.named_steps["model"].scale_pos_weight == pytest.approx((y == 0).sum() / (y == 1).sum())


@pytest.fixture(scope="module")
def tuned(xy, training_cfg, features_cfg, fast_opt_cfg):
    plan, X, y = xy
    return tune_all(X, y, plan, training_cfg, features_cfg, fast_opt_cfg, 42)


def test_tuning_ranks_candidates_and_includes_baseline(tuned, fast_opt_cfg):
    for name, res in tuned.items():
        assert res.model == name and res.primary_metric == "pr_auc"
        pr = [c.cv["pr_auc"]["mean"] for c in res.candidates]
        assert pr == sorted(pr, reverse=True)
        assert [c.rank for c in res.candidates] == list(range(1, len(pr) + 1))
        assert res.best is res.candidates[0] and res.baseline is not None and res.baseline.is_baseline
        # baseline competes => tuned CV score can never be below the baseline's
        assert res.best.cv["pr_auc"]["mean"] >= res.baseline.cv["pr_auc"]["mean"]
        assert res.n_candidates <= fast_opt_cfg["tuning"]["n_iter"][name] + 2
        assert all(c.cv["n_splits"] == fast_opt_cfg["tuning"]["cv"]["n_splits"] for c in res.candidates)


def test_tuning_is_reproducible(xy, tuned, training_cfg, features_cfg, fast_opt_cfg):
    plan, X, y = xy
    again = tune_model("logistic_regression", X, y, plan, training_cfg, features_cfg, fast_opt_cfg, 42)
    a, b = again.to_dict(), tuned["logistic_regression"].to_dict()
    a.pop("seconds"), b.pop("seconds")
    assert a == b


def test_different_seed_changes_sampled_candidates(xy, training_cfg, features_cfg, fast_opt_cfg):
    plan, X, y = xy
    a = tune_model("random_forest", X, y, plan, training_cfg, features_cfg, fast_opt_cfg, 1)
    b = tune_model("random_forest", X, y, plan, training_cfg, features_cfg, fast_opt_cfg, 2)
    assert {c.key() for c in a.candidates} != {c.key() for c in b.candidates}


def test_tuning_uses_stratified_cv_with_identical_folds(xy, training_cfg, features_cfg, fast_opt_cfg,
                                                        monkeypatch):
    from sklearn.model_selection import StratifiedKFold
    plan, X, y = xy
    seen = []
    real = tuning.cross_validate_pipeline

    def spy(pipe, X_, y_, n_splits=5, seed=42, cv=None):
        seen.append((n_splits, seed, len(X_)))
        return real(pipe, X_, y_, n_splits=n_splits, seed=seed, cv=cv)

    monkeypatch.setattr(tuning, "cross_validate_pipeline", spy)
    tune_model("logistic_regression", X, y, plan, training_cfg, features_cfg, fast_opt_cfg, 42)
    assert seen and len(set(seen)) == 1 and seen[0] == (3, 42, len(X))   # same folds for every candidate
    from ml.pipelines.evaluation import cv_splitter
    assert isinstance(cv_splitter(3, 42), StratifiedKFold) and cv_splitter(3, 42).shuffle


def test_unknown_model_rejected(xy, training_cfg, features_cfg, fast_opt_cfg):
    plan, X, y = xy
    with pytest.raises(ValueError, match="Unknown model"):
        tune_model("svm", X, y, plan, training_cfg, features_cfg, fast_opt_cfg, 1)


def test_tuning_functions_cannot_receive_validation_or_test_data():
    for fn in (tune_model, tune_all, build_candidate_pipeline, sample_configs):
        names = set(inspect.signature(fn).parameters)
        assert not {n for n in names if "test" in n or "val" in n.split("_")}, fn.__name__
