"""Phase 1.1: validation/test rows must not influence any target-informed or learned decision.

Every test builds explicit TRAIN / VALIDATION / TEST frames and feeds them to
``run_training_on_splits`` (the part of the flow after the split), so that only val/test content
changes between two runs. Each test has a control proving it would fail if isolation were broken.
"""
import inspect

import numpy as np
import pandas as pd
import pytest
from sklearn.base import BaseEstimator, TransformerMixin

import ml.pipelines.training as training
import ml.pipelines.validation as validation
from ml.errors import ValidationError
from ml.pipelines.preprocessing import plan_features, prepare_xy
from ml.pipelines.training import (
    run_training,
    run_training_on_splits,
    split_raw,
    train_models,
)
from ml.pipelines.validation import find_leakage_suspects, validate_training_data
from tests.conftest import make_churn_frame

MODELS = ["logistic_regression"]


# --------------------------------------------------------------------------- helpers
@pytest.fixture()
def splits(spec):
    """Deterministic raw TRAIN/VAL/TEST frames (copies, safe to mutate)."""
    raw = split_raw(make_churn_frame(1500, seed=3), spec, 0.15, 0.15, 42)
    return raw.train.copy(), raw.val.copy(), raw.test.copy()


@pytest.fixture()
def cfg(training_cfg):
    return {**training_cfg, "cv": {"n_splits": 3}}


def run(splits, spec, quality_cfg, cfg, features_cfg):
    tr, va, te = splits
    return run_training_on_splits(tr, va, te, spec, quality_cfg, cfg, features_cfg, models=MODELS)


def decisions(rep):
    """Everything that is a TRAIN-side decision or a CV result (must not depend on val/test)."""
    return {
        "training_validation": rep.training_validation,
        "feature_plan": rep.feature_plan,
        "engineered": rep.engineered_features,
        "cv": [r.cv for r in rep.results],
        "selected_imbalance": [(r.name, r.imbalance, r.selected_imbalance) for r in rep.results],
    }


def add_col(frames, name, train_vals, val_vals, test_vals):
    for f, v in zip(frames, (train_vals, val_vals, test_vals), strict=True):
        f[name] = v


def flip(labels: pd.Series) -> pd.Series:
    return labels.map({"Yes": "No", "No": "Yes"})


# --------------------------------------------------- Test 1: leakage-screening isolation
def sensitive(quality_cfg, **leak):
    """Lower the leakage threshold so a leak confined to val/test WOULD be flagged if pooled with
    TRAIN (default 0.99 is unreachable when only 15-30% of rows are leaky). Makes the tests discriminating."""
    return {**quality_cfg, "leakage": {**quality_cfg["leakage"], **leak}}


def test_leakage_screen_ignores_validation_and_test_labels(splits, spec, quality_cfg, cfg, features_cfg):
    quality_cfg = sensitive(quality_cfg, min_balanced_accuracy=0.56)
    tr, va, te = splits
    rng = np.random.default_rng(0)
    rnd = lambda n: rng.choice(["a", "b"], n)  # noqa: E731
    base = [f.copy() for f in (tr, va, te)]
    add_col(base, "ref_code", rnd(len(tr)), rnd(len(va)), rnd(len(te)))
    baseline = run(base, spec, quality_cfg, cfg, features_cfg)

    # Change ONLY val/test: flip every label and make the column a perfect copy of the new label.
    alt = [f.copy() for f in base]
    for f in alt[1:]:
        f["Churn"] = flip(f["Churn"])
        f["ref_code"] = np.where(f["Churn"] == "Yes", "a", "b")
    variant = run(alt, spec, quality_cfg, cfg, features_cfg)

    # control: pooled over all rows (old flow) the column WOULD be flagged at this threshold
    pooled = pd.concat(alt)
    assert "ref_code" in {c for c, _ in find_leakage_suspects(
        pooled, validation.encode_target(pooled["Churn"], "Yes"), ["ref_code"], [], "Churn", quality_cfg)}

    assert decisions(variant) == decisions(baseline)
    assert "POSSIBLE_TARGET_LEAKAGE" not in {e["code"] for e in variant.training_validation["errors"]}
    # sanity: the val labels ARE used for evaluation (metrics move) - only decisions are isolated
    assert variant.results[0].validation != baseline.results[0].validation


def test_leakage_screen_is_live_and_sees_train_only(splits, spec, quality_cfg, cfg, features_cfg, monkeypatch):
    tr, va, te = splits
    seen = []
    real = validation.find_leakage_suspects
    monkeypatch.setattr(validation, "find_leakage_suspects",
                        lambda df, y, *a, **k: (seen.append((set(df["customerID"]), len(y))),
                                                real(df, y, *a, **k))[1])
    run((tr, va, te), spec, quality_cfg, cfg, features_cfg)
    assert len(seen) == 1
    ids, n_labels = seen[0]
    assert ids == set(tr["customerID"]) and n_labels == len(tr)
    assert not ids & (set(va["customerID"]) | set(te["customerID"]))

    # positive control: the same leak placed in TRAIN is caught and rejects the run
    leaky = [f.copy() for f in (tr, va, te)]
    for f in leaky:
        f["Outcome"] = np.where(f["Churn"] == "Yes", "lost", "kept")
    monkeypatch.setattr(validation, "find_leakage_suspects", real)
    with pytest.raises(ValidationError, match="POSSIBLE_TARGET_LEAKAGE"):
        run(leaky, spec, quality_cfg, cfg, features_cfg)


# ------------------------------------------------------- Test 2: feature-planning isolation
def test_feature_plan_ignores_validation_and_test_features(splits, spec, quality_cfg, cfg, features_cfg):
    quality_cfg = {**quality_cfg, "limits": {**quality_cfg["limits"], "max_column_missing_fraction": 0.2}}
    tr, va, te = splits
    baseline = run((tr, va, te), spec, quality_cfg, cfg, features_cfg)
    assert baseline.feature_plan == {
        "numeric": plan_features(tr, spec, quality_cfg).numeric,
        "categorical": plan_features(tr, spec, quality_cfg).categorical,
        "dropped": plan_features(tr, spec, quality_cfg).dropped,
    }

    alt = [f.copy() for f in (tr, va, te)]
    for f in alt[1:]:  # wreck val/test features: all-null, constant, wild values, new-id-like
        f["Contract"] = np.nan                      # all-null in val/test
        f["PaymentMethod"] = "Mailed check"          # constant in val/test
        f["MonthlyCharges"] = 9e6                    # absurd values
        f["tenure"] = np.arange(len(f))              # id-like in val/test
        f["TotalCharges"] = "garbage"
    variant = run(alt, spec, quality_cfg, cfg, features_cfg)
    # control: planning on pooled rows (old flow) WOULD drop Contract (30% null > 20% limit)
    assert plan_features(pd.concat(alt), spec, quality_cfg).dropped.get("Contract") == "high_missing"
    assert "Contract" in baseline.feature_plan["categorical"]
    assert variant.feature_plan == baseline.feature_plan
    assert variant.engineered_features == baseline.engineered_features
    assert [r.cv for r in variant.results] == [r.cv for r in baseline.results]  # CV is train-only


# --------------------------------------------- Test 3: constant in TRAIN, variable in TEST
def test_constant_in_train_variable_in_test_follows_train(splits, spec, quality_cfg, cfg, features_cfg):
    tr, va, te = splits
    rng = np.random.default_rng(1)
    frames = [f.copy() for f in (tr, va, te)]
    add_col(frames, "promo", "A", rng.choice(["A", "B"], len(va)), rng.choice(["A", "B"], len(te)))

    assert plan_features(frames[0], spec, quality_cfg).dropped["promo"] == "constant"
    rep = run(frames, spec, quality_cfg, cfg, features_cfg)
    assert rep.feature_plan["dropped"]["promo"] == "constant"
    assert "promo" not in rep.feature_plan["categorical"]
    assert any(w["code"] == "FEATURE_DROPPED" and w["column"] == "promo"
               for w in rep.training_validation["warnings"])
    assert "promo" not in rep.results[0].pipeline.named_steps["coerce"].categorical

    # negative control: planning on the concatenated data (the old, leaky flow) would KEEP it
    assert "promo" in plan_features(pd.concat(frames), spec, quality_cfg).categorical

    # mirror case: variable in TRAIN, constant in val/test -> kept (TRAIN decides)
    mirror = [f.copy() for f in (tr, va, te)]
    add_col(mirror, "promo", rng.choice(["A", "B"], len(tr)), "A", "A")
    assert "promo" in run(mirror, spec, quality_cfg, cfg, features_cfg).feature_plan["categorical"]


# ----------------------------------------------------- Test 4: leakage-like only in TEST
def test_leak_like_feature_only_in_test_does_not_affect_selection(splits, spec, quality_cfg, cfg, features_cfg):
    quality_cfg = sensitive(quality_cfg, min_single_feature_auc=0.56)
    # At this sensitivity genuine numeric signals (tenure ...) would also be flagged on TRAIN, so keep
    # them out of this test; late_score is then the only numeric candidate for the screen.
    spec = type(spec)(**{**spec.to_dict(),
                         "exclude": ["tenure", "MonthlyCharges", "TotalCharges", "SeniorCitizen"]})
    tr, va, te = splits
    rng = np.random.default_rng(2)
    clean = [f.copy() for f in (tr, va, te)]
    add_col(clean, "late_score", rng.normal(size=len(tr)), rng.normal(size=len(va)), rng.normal(size=len(te)))
    leaky_test = [f.copy() for f in clean]
    # becomes (almost) a copy of the label in TEST only
    leaky_test[2]["late_score"] = (leaky_test[2]["Churn"] == "Yes") * 3.0 + rng.normal(0, 0.1, len(te))

    a = run(clean, spec, quality_cfg, cfg, features_cfg)
    b = run(leaky_test, spec, quality_cfg, cfg, features_cfg)  # must NOT raise
    assert "late_score" in b.feature_plan["numeric"]                  # still a normal feature
    assert not b.training_validation["errors"]
    assert decisions(a) == decisions(b)

    # controls: the screen WOULD flag it on the pooled rows (old flow) and on the test rows alone
    for frame in (pd.concat(leaky_test), leaky_test[2]):
        y = validation.encode_target(frame["Churn"], "Yes")
        assert "late_score" in {c for c, _ in find_leakage_suspects(
            frame, y, ["late_score"], ["late_score"], "Churn", quality_cfg)}


# --------------------------------- Test 5: TEST (and VAL) never passed to fit/selection code
class Recorder(BaseEstimator, TransformerMixin):
    """Records the `src` marker values seen at fit and at transform time (class-level)."""
    fit_src: list = []
    transform_src: list = []

    def fit(self, X, y=None):
        Recorder.fit_src.append(set(X["src"].dropna()))
        return self

    def transform(self, X):
        Recorder.transform_src.append(set(X["src"].dropna()))
        return X


def test_only_train_reaches_planning_screening_cv_and_fitting(splits, spec, quality_cfg, cfg,
                                                              features_cfg, monkeypatch):
    tr, va, te = splits
    rng = np.random.default_rng(3)
    frames = [f.copy() for f in (tr, va, te)]
    add_col(frames, "src", rng.choice(["t_a", "t_b"], len(tr)),
            rng.choice(["v_a", "v_b"], len(va)), rng.choice(["x_a", "x_b"], len(te)))
    tr, va, te = frames

    calls = {"plan": [], "leak": [], "cv": []}
    real_plan, real_leak = training.plan_features, validation.find_leakage_suspects
    real_cv, real_build = training.cross_validate_pipeline, training.build_pipeline

    def plan_spy(df, *a, **k):
        calls["plan"].append(set(df["src"]))
        return real_plan(df, *a, **k)

    def leak_spy(df, y, *a, **k):
        calls["leak"].append((set(df["src"]), len(y)))
        return real_leak(df, y, *a, **k)

    def cv_spy(pipe, X, y, *a, **k):
        calls["cv"].append((set(X["src"]), len(X), len(y)))
        return real_cv(pipe, X, y, *a, **k)

    def build_spy(plan, est, fcfg):
        pipe = real_build(plan, est, fcfg)
        pipe.steps.insert(1, ("rec", Recorder()))
        return pipe

    Recorder.fit_src, Recorder.transform_src = [], []
    monkeypatch.setattr(training, "plan_features", plan_spy)
    monkeypatch.setattr(validation, "find_leakage_suspects", leak_spy)
    monkeypatch.setattr(training, "cross_validate_pipeline", cv_spy)
    monkeypatch.setattr(training, "build_pipeline", build_spy)

    rep = run_training_on_splits(tr, va, te, spec, quality_cfg, cfg, features_cfg, models=MODELS)

    only_train = {"t_a", "t_b"}
    assert calls["plan"] == [only_train]                                  # feature planning
    assert calls["leak"] == [(only_train, len(tr))]                       # leakage screening
    assert calls["cv"] and all(c == (only_train, len(tr), len(tr)) for c in calls["cv"])  # CV
    assert Recorder.fit_src and all(s <= only_train for s in Recorder.fit_src)  # every fit (CV + final)
    seen_by_transform = set().union(*Recorder.transform_src)
    assert seen_by_transform <= {"t_a", "t_b", "v_a", "v_b"}              # val is scored, TEST never
    assert not any(v.startswith("x_") for v in seen_by_transform | set().union(*Recorder.fit_src))
    assert rep.split_sizes["test"] == len(te)


class OnlyLen:
    """Stand-in for the TEST frame: supports len() and nothing else (no columns, no concat, no copy)."""

    def __init__(self, n: int):
        self.n = n

    def __len__(self):
        return self.n


def test_test_frame_is_never_read_in_phase1(splits, spec, quality_cfg, cfg, features_cfg):
    tr, va, te = splits
    reference = run((tr, va, te), spec, quality_cfg, cfg, features_cfg)
    guarded = run_training_on_splits(tr, va, OnlyLen(len(te)), spec, quality_cfg, cfg, features_cfg,
                                     models=MODELS)  # any read/concat/column access of TEST raises
    assert guarded.split_sizes == reference.split_sizes
    assert guarded.results[0].validation == reference.results[0].validation
    assert decisions(guarded) == decisions(reference)
    with pytest.raises(TypeError):  # control: the sentinel really cannot be pooled or indexed
        pd.concat([tr, OnlyLen(3)])


def test_run_training_end_to_end_only_train_rows_reach_decision_functions(
        df, spec, quality_cfg, cfg, features_cfg, monkeypatch):
    """Full orchestrator: planning, screening and CV receive exactly the TRAIN split."""
    raw = split_raw(df, spec, 0.15, 0.15, cfg["seed"])
    train_ids = set(raw.train["customerID"])
    other_ids = set(raw.val["customerID"]) | set(raw.test["customerID"])
    X_train_expected, _, _ = prepare_xy(raw.train, spec, plan_features(raw.train, spec, quality_cfg))

    seen = {"plan": [], "leak": [], "cv": []}
    real_plan, real_leak, real_cv = (training.plan_features, validation.find_leakage_suspects,
                                     training.cross_validate_pipeline)
    monkeypatch.setattr(training, "plan_features",
                        lambda d, *a, **k: (seen["plan"].append(set(d["customerID"])), real_plan(d, *a, **k))[1])
    monkeypatch.setattr(validation, "find_leakage_suspects",
                        lambda d, y, *a, **k: (seen["leak"].append(set(d["customerID"])),
                                               real_leak(d, y, *a, **k))[1])

    def cv_spy(pipe, X, y, *a, **k):
        seen["cv"].append(X)
        return real_cv(pipe, X, y, *a, **k)

    monkeypatch.setattr(training, "cross_validate_pipeline", cv_spy)
    run_training(df, spec, quality_cfg, cfg, features_cfg, models=MODELS)

    assert seen["plan"] == [train_ids] and seen["leak"] == [train_ids]
    assert all(not (s & other_ids) for s in seen["plan"] + seen["leak"])
    assert seen["cv"] and all(X.equals(X_train_expected) for X in seen["cv"])


def test_function_signatures_cannot_receive_val_or_test():
    for fn in (train_models, validate_training_data, find_leakage_suspects, plan_features):
        names = set(inspect.signature(fn).parameters)
        assert not {n for n in names if "test" in n}, fn.__name__
    assert list(inspect.signature(validate_training_data).parameters) == ["train_df", "spec", "cfg", "plan"]
    assert not {"X_val", "val_df"} & set(inspect.signature(validate_training_data).parameters)


def test_split_raw_matches_legacy_partition_and_is_stratified(df, spec, quality_cfg):
    """Reproducibility: same seed/ratios/stratification as splitting (X, y) after planning."""
    from ml.pipelines.training import split_data
    plan = plan_features(df, spec, quality_cfg)
    X, y, ids = prepare_xy(df, spec, plan)
    legacy = split_data(X, y, 0.15, 0.15, 42)
    raw = split_raw(df, spec, 0.15, 0.15, 42)
    assert list(raw.train["customerID"]) == list(ids.loc[legacy.X_train.index])
    assert list(raw.val["customerID"]) == list(ids.loc[legacy.X_val.index])
    assert list(raw.test["customerID"]) == list(ids.loc[legacy.X_test.index])
    for part, yy in ((raw.train, legacy.y_train), (raw.val, legacy.y_val), (raw.test, legacy.y_test)):
        assert ((part["Churn"] == "Yes").mean() == pytest.approx(yy.mean(), abs=1e-12))
