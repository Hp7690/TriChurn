"""Phase 2 - calibration: fitted on TRAIN out-of-fold predictions, compared on VALIDATION."""
import inspect

import numpy as np
import pytest

from ml.pipelines import calibration as cal
from ml.pipelines.calibration import (
    CalibratedModel,
    IdentityCalibrator,
    IsotonicCalibrator,
    SigmoidCalibrator,
    calibrate_and_select,
    fit_calibrated_candidates,
    make_calibrator,
    out_of_fold_probabilities,
    reliability_table,
)
from ml.pipelines.evaluation import probability_metrics
from ml.pipelines.preprocessing import plan_features, prepare_xy
from ml.pipelines.training import split_raw
from ml.pipelines.tuning import build_candidate_pipeline
from tests.conftest import make_churn_frame


def sigmoid(z):
    return 1 / (1 + np.exp(-z))


def miscalibrated(n, seed):
    """raw scores whose true churn probability is sigmoid(2*logit(raw)+1): systematically under-confident."""
    rng = np.random.default_rng(seed)
    raw = rng.uniform(0.02, 0.98, n)
    true_p = sigmoid(2 * np.log(raw / (1 - raw)) + 1)
    return raw, (rng.random(n) < true_p).astype(int)


def test_sigmoid_recovers_platt_parameters():
    p, y = miscalibrated(40000, 0)
    params = SigmoidCalibrator().fit(p, y).parameters()
    assert params["a"] == pytest.approx(2.0, abs=0.1) and params["b"] == pytest.approx(1.0, abs=0.1)


@pytest.mark.parametrize("method", ["sigmoid", "isotonic"])
def test_calibrators_reduce_brier_and_log_loss_on_heldout_data(method):
    p_tr, y_tr = miscalibrated(8000, 1)
    p_te, y_te = miscalibrated(8000, 2)
    before = probability_metrics(y_te, p_te)
    q = make_calibrator(method).fit(p_tr, y_tr).transform(p_te)
    after = probability_metrics(y_te, q)
    assert after["brier"] < before["brier"] and after["log_loss"] < before["log_loss"]
    assert np.all((q >= 0) & (q <= 1))


def test_calibrators_are_monotone_and_identity_is_noop():
    p, y = miscalibrated(3000, 3)
    grid = np.linspace(0, 1, 201)
    for method in ("sigmoid", "isotonic"):
        out = make_calibrator(method).fit(p, y).transform(grid)
        assert np.all(np.diff(out) >= -1e-12), method
    assert np.allclose(IdentityCalibrator().fit(p, y).transform(grid), grid)
    assert isinstance(make_calibrator("isotonic"), IsotonicCalibrator)
    with pytest.raises(ValueError, match="Unknown calibration method"):
        make_calibrator("beta")


def test_reliability_table_and_ece_known_values():
    rows, ece = reliability_table([0, 1, 0, 1], [0.5, 0.5, 0.5, 0.5], n_bins=10)
    assert ece == pytest.approx(0.0) and rows[0]["n"] == 4
    _, ece = reliability_table([0, 0, 0, 0], [0.9, 0.9, 0.9, 0.9])
    assert ece == pytest.approx(0.9)


@pytest.fixture(scope="module")
def fitted(spec, quality_cfg, training_cfg, features_cfg):
    """Class-weighted LR (over-predicts churn => miscalibrated) fitted on TRAIN of imbalanced data."""
    raw = split_raw(make_churn_frame(2500, seed=9, churn_target_rate=0.12), spec, 0.15, 0.15, 42)
    plan = plan_features(raw.train, spec, quality_cfg)
    Xt, yt, _ = prepare_xy(raw.train, spec, plan)
    Xv, yv, _ = prepare_xy(raw.val, spec, plan)
    base = build_candidate_pipeline("logistic_regression", "balanced", {"C": 1.0, "max_iter": 2000}, yt, plan,
                                    features_cfg, 42)
    base.fit(Xt, yt)
    return dict(base=base, Xt=Xt, yt=yt, Xv=Xv, yv=yv)


def test_oof_probabilities_cover_train_exactly_once(fitted):
    oof = out_of_fold_probabilities(fitted["base"], fitted["Xt"], fitted["yt"], 3, 42)
    assert oof.shape == (len(fitted["Xt"]),) and np.all((oof >= 0) & (oof <= 1))
    assert np.array_equal(oof, out_of_fold_probabilities(fitted["base"], fitted["Xt"], fitted["yt"], 3, 42))


def test_calibrators_are_fitted_on_train_sized_data_only(fitted, monkeypatch):
    sizes = []
    for klass in (cal.SigmoidCalibrator, cal.IsotonicCalibrator):
        real = klass.fit
        monkeypatch.setattr(klass, "fit", lambda self, p, y, _r=real: (sizes.append((len(p), len(y))),
                                                                       _r(self, p, y))[1])
    models = fit_calibrated_candidates(fitted["base"], fitted["Xt"], fitted["yt"],
                                       ["none", "sigmoid", "isotonic"], 3, 42)
    assert set(models) == {"none", "sigmoid", "isotonic"}
    assert sizes == [(len(fitted["Xt"]), len(fitted["Xt"]))] * 2
    assert all(isinstance(m, CalibratedModel) and m.base is fitted["base"] for m in models.values())


def test_calibrated_model_outputs_valid_probability_matrix(fitted):
    m = fit_calibrated_candidates(fitted["base"], fitted["Xt"], fitted["yt"], ["sigmoid"], 3, 42)["sigmoid"]
    P = m.predict_proba(fitted["Xv"])
    assert P.shape == (len(fitted["Xv"]), 2) and np.allclose(P.sum(axis=1), 1) and np.all((P >= 0) & (P <= 1))
    assert set(m.calibration_parameters()) == {"method", "a", "b"}


def test_calibration_improves_brier_of_class_weighted_model_and_is_selected(fitted):
    cfg = {"methods": ["none", "sigmoid", "isotonic"], "select_by": "brier", "cv_folds": 3}
    res = calibrate_and_select(fitted["base"], fitted["Xt"], fitted["yt"], fitted["Xv"], fitted["yv"], cfg, 42)
    assert res.method in ("sigmoid", "isotonic")
    none, chosen = res.candidates["none"], res.candidates[res.method]
    assert chosen["brier"] < none["brier"] and chosen["log_loss"] < none["log_loss"]
    assert chosen["ece"] < none["ece"]
    assert res.candidates[res.method]["brier"] == min(c["brier"] for c in res.candidates.values())
    assert res.parameters == res.model.calibration_parameters() and res.model.method == res.method
    # ROC-AUC of sigmoid calibration is rank-preserving
    assert res.candidates["sigmoid"]["roc_auc"] == pytest.approx(res.candidates["none"]["roc_auc"], abs=1e-9)


def test_selection_metric_and_tie_order_are_configurable(fitted):
    cfg = {"methods": ["none", "sigmoid"], "select_by": "log_loss", "cv_folds": 3}
    res = calibrate_and_select(fitted["base"], fitted["Xt"], fitted["yt"], fitted["Xv"], fitted["yv"], cfg, 42)
    assert res.select_by == "log_loss" and set(res.candidates) == {"none", "sigmoid"}
    only_none = calibrate_and_select(fitted["base"], fitted["Xt"], fitted["yt"], fitted["Xv"], fitted["yv"],
                                     {**cfg, "methods": ["none"]}, 42)
    assert only_none.method == "none" and only_none.parameters == {"method": "none"}
    with pytest.raises(ValueError, match="select_by"):
        calibrate_and_select(fitted["base"], fitted["Xt"], fitted["yt"], fitted["Xv"], fitted["yv"],
                             {**cfg, "select_by": "auc"}, 42)


def test_calibration_functions_cannot_receive_test_data():
    for fn in (calibrate_and_select, fit_calibrated_candidates, out_of_fold_probabilities, reliability_table):
        assert not {n for n in inspect.signature(fn).parameters if "test" in n}, fn.__name__


def test_parsimony_margin_keeps_simpler_method_unless_gain_is_material(fitted):
    base = dict(methods=["none", "sigmoid", "isotonic"], select_by="brier", cv_folds=3)
    args = (fitted["base"], fitted["Xt"], fitted["yt"], fitted["Xv"], fitted["yv"])
    plain = calibrate_and_select(*args, {**base, "min_improvement": 0.0}, 42)
    assert plain.candidates[plain.method]["brier"] == min(c["brier"] for c in plain.candidates.values())
    # an unreachable margin: nothing beats `none` by that much -> the simplest method is kept
    assert calibrate_and_select(*args, {**base, "min_improvement": 10.0}, 42).method == "none"
    # the class-weighted model is badly calibrated, so a realistic margin still selects a calibrator
    assert calibrate_and_select(*args, {**base, "min_improvement": 0.0005}, 42).method in ("sigmoid", "isotonic")
    # an already well-calibrated model (identity-calibrated candidates ~ equal) keeps `none` inside the margin
    good = calibrate_and_select(*args, {**base, "methods": ["none", "none"], "min_improvement": 0.0005}, 42)
    assert good.method == "none"


def test_default_config_enables_parsimony(optimization_cfg):
    assert optimization_cfg["calibration"]["min_improvement"] > 0
    assert optimization_cfg["calibration"]["methods"][0] == "none"
