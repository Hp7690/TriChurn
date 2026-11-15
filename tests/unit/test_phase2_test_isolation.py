"""Phase 2 TEST ISOLATION. The held-out test split must not influence tuning, model selection, calibration,
threshold choice, or the lock - and must only be read after everything is locked, exactly once.

Each equality test is paired with a control proving the compared quantity IS sensitive to the data it is
supposed to depend on (so a pass cannot be vacuous).
"""
import ast
import inspect
import textwrap

import numpy as np
import pytest
from sklearn.base import BaseEstimator, TransformerMixin

import ml.pipelines.calibration as calibration_mod
import ml.pipelines.model_selection as selection_mod
import ml.pipelines.optimization as opt
import ml.pipelines.thresholding as threshold_mod
import ml.pipelines.tuning as tuning_mod
from ml.pipelines.calibration import fit_calibrated_candidates
from ml.pipelines.final_evaluation import evaluate_on_test
from ml.pipelines.optimization import run_optimization_decisions, run_optimization_on_splits
from ml.pipelines.training import split_raw
from tests.conftest import make_churn_frame

MODELS = ["logistic_regression", "random_forest", "xgboost"]   # real selection among all three


@pytest.fixture(scope="module")
def splits(spec):
    raw = split_raw(make_churn_frame(1500, seed=41), spec, 0.15, 0.15, 42)
    return raw.train.copy(), raw.val.copy(), raw.test.copy()


def go(splits_, spec, quality_cfg, training_cfg, features_cfg, opt_cfg):
    tr, va, te = splits_
    return run_optimization_on_splits(tr, va, te, spec, quality_cfg, training_cfg, features_cfg, opt_cfg,
                                      models=MODELS)


def decision_state(rep):
    """Every TRAIN/VALIDATION-side decision and score. Must be a pure function of (train, validation)."""
    d = rep.decisions
    return {
        "tuning": {m: t.to_dict() | {"seconds": 0} for m, t in d.tuning.items()},
        "comparison": d.comparison.to_dict(),
        "calibration": d.calibration.to_dict(),
        "threshold": d.threshold.to_dict(),
        "validation_final": d.validation_final,
        "locked": d.locked.decisions(),
    }
def assert_decision_structures_equal(actual, expected, *, rel_tol=1e-12, abs_tol=1e-12):
    """Compare decision structures while allowing harmless FP rounding noise."""
    if isinstance(actual, dict) and isinstance(expected, dict):
        assert actual.keys() == expected.keys()
        for key in actual:
            assert_decision_structures_equal(
                actual[key], expected[key],
                rel_tol=rel_tol, abs_tol=abs_tol,
            )
        return

    if isinstance(actual, (list, tuple)) and isinstance(expected, (list, tuple)):
        assert len(actual) == len(expected)
        for a_item, e_item in zip(actual, expected, strict=False):
            assert_decision_structures_equal(
                a_item, e_item,
                rel_tol=rel_tol, abs_tol=abs_tol,
            )
        return

    if isinstance(actual, (float, np.floating)) and isinstance(expected, (float, np.floating)):
        assert np.isclose(actual, expected, rtol=rel_tol, atol=abs_tol, equal_nan=True)
        return

    assert actual == expected



@pytest.fixture(scope="module")
def baseline(splits, spec, quality_cfg, training_cfg, features_cfg, fast_opt_cfg):
    return go(splits, spec, quality_cfg, training_cfg, features_cfg, fast_opt_cfg)


def _variants(te):
    flipped = te.copy()
    flipped["Churn"] = flipped["Churn"].map({"Yes": "No", "No": "Yes"})
    wrecked = te.copy()
    rng = np.random.default_rng(0)
    wrecked["Churn"] = rng.choice(["Yes", "No"], len(te))
    wrecked["Contract"] = "Two year"
    wrecked["tenure"] = 0
    wrecked["MonthlyCharges"] = 9e6
    wrecked["TotalCharges"] = "garbage"
    other = make_churn_frame(len(te) + 77, seed=999, churn_target_rate=0.6)   # a different test population
    return {"flipped_labels": flipped, "wrecked_features_random_labels": wrecked, "different_population": other}


@pytest.mark.parametrize("variant", ["flipped_labels", "wrecked_features_random_labels", "different_population"])
def test_changing_test_data_changes_no_decision(variant, baseline, splits, spec, quality_cfg, training_cfg,
                                                features_cfg, fast_opt_cfg):
    tr, va, te = splits
    alt = go((tr, va, _variants(te)[variant]), spec, quality_cfg, training_cfg, features_cfg, fast_opt_cfg)
    a, b = decision_state(baseline), decision_state(alt)
    # tuning decisions
    assert b["tuning"] == a["tuning"]
    assert {m: t.best.to_dict() for m, t in alt.decisions.tuning.items()} == \
           {m: t.best.to_dict() for m, t in baseline.decisions.tuning.items()}
    # model selection
    assert alt.decisions.comparison.selected == baseline.decisions.comparison.selected
    assert_decision_structures_equal(b["comparison"], a["comparison"])
    # calibration (method, fitted parameters, validation comparison)
    assert alt.decisions.calibration.method == baseline.decisions.calibration.method
    assert b["calibration"] == a["calibration"]
    assert alt.decisions.calibration.model.calibration_parameters() == \
           baseline.decisions.calibration.model.calibration_parameters()
    # threshold
    assert alt.decisions.threshold.threshold == baseline.decisions.threshold.threshold
    assert b["threshold"] == a["threshold"] and b["validation_final"] == a["validation_final"]
    # the whole lock
    assert b["locked"] == a["locked"]
    # control: the test data WAS consumed (final numbers differ) - only decisions are isolated
    assert alt.final.to_dict() != baseline.final.to_dict()
    assert alt.final.lock_fingerprint == baseline.final.lock_fingerprint


def test_control_decisions_do_respond_to_train_and_validation_data(splits, baseline, spec, quality_cfg,
                                                                    training_cfg, features_cfg, fast_opt_cfg):
    """If the comparisons above were vacuous these would not move either."""
    tr, va, _ = splits
    flip = lambda f: f.assign(Churn=f["Churn"].map({"Yes": "No", "No": "Yes"}))  # noqa: E731
    val_flipped = run_optimization_decisions(tr, flip(va), spec, quality_cfg, training_cfg, features_cfg,
                                             fast_opt_cfg, MODELS)
    assert val_flipped.threshold.to_dict() != baseline.decisions.threshold.to_dict()
    assert val_flipped.calibration.candidates != baseline.decisions.calibration.candidates
    assert val_flipped.locked.fingerprint != baseline.decisions.locked.fingerprint
    # same TRAIN => identical tuning even though validation changed (tuning is TRAIN-only)
    assert {m: t.to_dict() | {"seconds": 0} for m, t in val_flipped.tuning.items()} == \
           decision_state(baseline)["tuning"]
    train_flipped = run_optimization_decisions(flip(tr), va, spec, quality_cfg, training_cfg, features_cfg,
                                               fast_opt_cfg, ["logistic_regression"])
    assert train_flipped.tuning["logistic_regression"].best.cv != \
           baseline.decisions.tuning["logistic_regression"].best.cv


# ----------------------------------------------------------- structural: where test can/can't flow
DECISION_FUNCTIONS = [
    tuning_mod.tune_all, tuning_mod.tune_model, tuning_mod.build_candidate_pipeline,
    selection_mod.compare_models, selection_mod.composite_score,
    calibration_mod.calibrate_and_select, calibration_mod.fit_calibrated_candidates,
    calibration_mod.out_of_fold_probabilities, threshold_mod.optimize_threshold, opt.run_optimization_decisions,
]


def test_no_decision_function_has_a_test_parameter():
    for fn in DECISION_FUNCTIONS:
        assert not {n for n in inspect.signature(fn).parameters if "test" in n.lower()}, fn.__qualname__
    assert list(inspect.signature(evaluate_on_test).parameters) == ["locked", "test_df", "spec"]


def test_decision_modules_never_mention_test_data_in_code():
    """Static scan: identifiers/arguments/attributes in the decision code must not refer to a test split."""
    modules = [tuning_mod, selection_mod, calibration_mod, threshold_mod]
    sources = [inspect.getsource(m) for m in modules] + [
        textwrap.dedent(inspect.getsource(opt.run_optimization_decisions))]
    for src in sources:
        for node in ast.walk(ast.parse(src)):
            ident = (getattr(node, "id", None) or getattr(node, "arg", None) or
                     getattr(node, "attr", None) or getattr(node, "name", None))
            if isinstance(ident, str):
                assert "test" not in ident.lower(), (ident, getattr(node, "lineno", None))
    # control: the scan would catch a leak
    leaky = ast.parse("def f(X_test):\n    return X_test.mean()")
    assert any("test" in (getattr(n, "arg", None) or getattr(n, "id", None) or "") for n in ast.walk(leaky))


def test_test_is_read_last_exactly_once_after_the_lock(splits, spec, quality_cfg, training_cfg, features_cfg,
                                                      fast_opt_cfg, monkeypatch):
    tr, va, te = splits
    events, seen = [], {}

    def wrap(module, name, label):
        real = getattr(module, name)

        def inner(*a, **k):
            events.append(label)
            seen[label] = (a, k)
            return real(*a, **k)
        monkeypatch.setattr(module, name, inner)

    for name, label in [("tune_all", "tune"), ("compare_models", "compare"),
                        ("calibrate_and_select", "calibrate"), ("optimize_threshold", "threshold"),
                        ("lock_model", "lock"), ("evaluate_on_test", "test")]:
        wrap(opt, name, label)
    rep = run_optimization_on_splits(tr, va, te, spec, quality_cfg, training_cfg, features_cfg, fast_opt_cfg,
                                     models=["logistic_regression"])
    assert events == ["tune", "compare", "calibrate", "threshold", "lock", "test"]    # test strictly last
    locked_arg, test_arg, _ = seen["test"][0]
    assert test_arg is te and locked_arg is rep.decisions.locked
    # nothing before the lock received the test frame object
    for label in ("tune", "compare", "calibrate", "threshold", "lock"):
        a, k = seen[label]
        assert all(obj is not te for obj in list(a) + list(k.values())), label
    assert rep.decisions.locked.test_consumed is True


class Recorder(BaseEstimator, TransformerMixin):
    fit_src: list = []
    transform_src: list = []

    def fit(self, X, y=None):
        Recorder.fit_src.append(set(X["src"].dropna()))
        return self

    def transform(self, X):
        Recorder.transform_src.append(set(X["src"].dropna()))
        return X


def test_markers_prove_test_rows_reach_no_fit_cv_calibration_or_threshold(splits, spec, quality_cfg,
                                                                           training_cfg, features_cfg,
                                                                           fast_opt_cfg, monkeypatch):
    tr, va, te = (f.copy() for f in splits)
    rng = np.random.default_rng(5)
    tr["src"] = rng.choice(["t_a", "t_b"], len(tr))
    va["src"] = rng.choice(["v_a", "v_b"], len(va))
    te["src"] = rng.choice(["x_a", "x_b"], len(te))

    real_build = tuning_mod.build_pipeline

    def build_spy(plan, est, fcfg):
        pipe = real_build(plan, est, fcfg)
        pipe.steps.insert(1, ("rec", Recorder()))
        return pipe

    sizes = {"tune": [], "cal": [], "thr": []}
    real_tune, real_cal, real_thr = opt.tune_all, opt.calibrate_and_select, opt.optimize_threshold
    monkeypatch.setattr(opt, "tune_all", lambda X, y, *a, **k: (sizes["tune"].append((len(X), len(y))),
                                                                 real_tune(X, y, *a, **k))[1])
    monkeypatch.setattr(opt, "calibrate_and_select",
                        lambda base, Xt, yt, Xv, yv, *a, **k: (sizes["cal"].append((len(Xt), len(Xv))),
                                                                real_cal(base, Xt, yt, Xv, yv, *a, **k))[1])
    monkeypatch.setattr(opt, "optimize_threshold", lambda y, p, c: (sizes["thr"].append((len(y), len(p))),
                                                                     real_thr(y, p, c))[1])
    monkeypatch.setattr(tuning_mod, "build_pipeline", build_spy)
    Recorder.fit_src, Recorder.transform_src = [], []

    dec = run_optimization_decisions(tr, va, spec, quality_cfg, training_cfg, features_cfg, fast_opt_cfg, MODELS)

    train_only, train_val = {"t_a", "t_b"}, {"t_a", "t_b", "v_a", "v_b"}
    assert Recorder.fit_src and all(s <= train_only for s in Recorder.fit_src)      # every fit: tuning CV, refits, OOF
    seen = set().union(*Recorder.transform_src)
    assert seen <= train_val and not any(v.startswith("x_") for v in seen)          # scoring: train/val only
    assert sizes["tune"] == [(len(tr), len(tr))]
    assert sizes["cal"][0][0] == len(tr) and sizes["cal"][0][1] == len(va)
    assert sizes["thr"] == [(len(va), len(va))]
    n_transforms_before = len(Recorder.transform_src)
    assert dec.locked.test_consumed is False

    n_fits_before = len(Recorder.fit_src)
    evaluate_on_test(dec.locked, te, spec)                                          # NOW the test is read
    after = Recorder.transform_src[n_transforms_before:]
    # test rows are scored; the lock-fingerprint check re-scores the 50 VALIDATION probe rows (v_), never train
    assert {"x_a", "x_b"} in after and set().union(*after) <= {"v_a", "v_b", "x_a", "x_b"}
    assert len(Recorder.fit_src) == n_fits_before                                    # nothing fitted on test
    assert dec.locked.test_consumed is True


def test_calibrator_is_exactly_reproducible_from_train_alone(splits, spec, baseline):
    """The selected calibrator's fitted parameters are re-derived from TRAIN only (no validation, no test
    rows involved), and equal the ones locked in the pipeline - so no test label can have shaped them."""
    from ml.pipelines.preprocessing import prepare_xy
    tr, _, _ = splits
    dec = baseline.decisions
    Xt, yt, _ = prepare_xy(tr, spec, dec.plan)
    base = dec.comparison.selected_evaluation.pipeline
    method = dec.calibration.method
    refit = fit_calibrated_candidates(base, Xt, yt, [method], 3, dec.locked.seed)[method]
    assert refit.calibration_parameters() == dec.calibration.model.calibration_parameters()
    # control: a calibrator fitted on label-flipped TRAIN differs (parameters do depend on the fitting labels)
    if method != "none":
        flipped = fit_calibrated_candidates(base, Xt, 1 - yt, [method], 3, dec.locked.seed)[method]
        assert flipped.calibration_parameters() != refit.calibration_parameters()
