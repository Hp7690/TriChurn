"""Phase 2 - threshold optimisation on VALIDATION."""
import inspect

import numpy as np
import pytest

from ml.pipelines.evaluation import compute_metrics
from ml.pipelines.thresholding import optimize_threshold, precision_recall_at, threshold_grid

GRID = {"start": 0.05, "stop": 0.95, "step": 0.01}


def cfg(**kw):
    return {"metric": "f1", "beta": 1.0, "min_precision": 0.5, "grid": GRID, "override": None, **kw}


def toy(n=600, seed=0, shift=0.0):
    """Probabilities whose F1-optimal threshold is well below 0.5 (low base rate)."""
    rng = np.random.default_rng(seed)
    y = (rng.random(n) < 0.2).astype(int)
    p = np.clip(np.where(y == 1, rng.beta(4, 5, n), rng.beta(1.5, 7, n)) + shift, 0.001, 0.999)
    return y, p


def test_grid_is_inclusive_and_configurable():
    g = threshold_grid(GRID)
    assert g[0] == 0.05 and g[-1] == pytest.approx(0.95) and len(g) == 91
    assert len(threshold_grid({"start": 0.1, "stop": 0.9, "step": 0.1})) == 9


def test_f1_threshold_matches_brute_force_and_is_not_default_half():
    y, p = toy()
    res = optimize_threshold(y, p, cfg())
    grid = threshold_grid(GRID)
    f1s = [compute_metrics(y, p, t)["f1"] for t in grid]
    assert res.f1 == pytest.approx(max(f1s)) and res.objective == pytest.approx(max(f1s))
    assert abs(f1s[int(np.argmax(np.isclose(grid, res.threshold)))] - max(f1s)) < 1e-12
    assert res.threshold != 0.5 and res.threshold < 0.5
    assert res.source == "optimized" and res.metric == "f1"


def test_reported_precision_recall_f1_match_compute_metrics_at_threshold():
    y, p = toy(seed=1)
    res = optimize_threshold(y, p, cfg())
    m = compute_metrics(y, p, res.threshold)
    assert (res.precision, res.recall, res.f1) == (pytest.approx(m["precision"]), pytest.approx(m["recall"]),
                                                   pytest.approx(m["f1"]))
    prec, rec, f1 = precision_recall_at(y, p, [res.threshold])
    assert prec[0] == pytest.approx(res.precision)


def test_plateau_uses_median_threshold():
    y = np.array([0, 0, 1, 1])
    p = np.array([0.1, 0.2, 0.8, 0.9])       # F1 = 1 for every threshold in (0.2, 0.8]
    res = optimize_threshold(y, p, cfg())
    assert res.f1 == 1.0 and res.n_tied > 3 and 0.3 < res.threshold < 0.7


def test_fbeta_prefers_recall_and_recall_at_precision_respects_constraint():
    y, p = toy(seed=2)
    f1 = optimize_threshold(y, p, cfg())
    f2 = optimize_threshold(y, p, cfg(metric="f_beta", beta=2.0))
    assert f2.threshold <= f1.threshold and f2.recall >= f1.recall
    rp = optimize_threshold(y, p, cfg(metric="recall_at_precision", min_precision=0.45))
    assert rp.precision >= 0.45
    prec, rec, _ = precision_recall_at(y, p, threshold_grid(GRID))
    assert rp.recall == pytest.approx(rec[prec >= 0.45].max())
    rng = np.random.default_rng(0)
    uninformative = rng.uniform(0.05, 0.95, len(y))          # precision ~ base rate (0.2) at every threshold
    with pytest.raises(ValueError, match="No threshold"):
        optimize_threshold(y, uninformative, cfg(metric="recall_at_precision", min_precision=0.9))


def test_override_is_honoured_and_reported_with_validation_metrics():
    y, p = toy()
    res = optimize_threshold(y, p, cfg(override=0.42))
    m = compute_metrics(y, p, 0.42)
    assert res.threshold == 0.42 and res.source == "configured"
    assert res.recall == pytest.approx(m["recall"]) and res.precision == pytest.approx(m["precision"])


def test_unknown_metric_rejected():
    y, p = toy()
    with pytest.raises(ValueError, match="Unknown threshold metric"):
        optimize_threshold(y, p, cfg(metric="accuracy"))


def test_threshold_depends_only_on_validation_labels_and_probabilities():
    assert list(inspect.signature(optimize_threshold).parameters) == ["y_val", "p_val", "th_cfg"]
    y, p = toy(seed=3)
    assert optimize_threshold(y, p, cfg()).threshold == optimize_threshold(y.copy(), p.copy(), cfg()).threshold
    # control: different validation labels give a different threshold (the function is label-sensitive)
    flipped = optimize_threshold(1 - y, p, cfg())
    assert flipped.threshold != optimize_threshold(y, p, cfg()).threshold
