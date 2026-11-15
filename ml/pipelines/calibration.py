"""Phase 2 - probability calibration (fitted on TRAIN, compared on VALIDATION).

Method (equivalent in spirit to ``CalibratedClassifierCV(cv=K, ensemble=False)`` but with inspectable
parameters):

1. Out-of-fold probabilities of the selected pipeline are produced on TRAIN with stratified K-fold
   (the whole pipeline is re-fitted per fold, so nothing leaks).
2. A calibrator maps raw probability -> calibrated probability, and is fitted on those TRAIN
   out-of-fold predictions and the TRAIN labels only:
      * ``sigmoid``  - Platt scaling on the log-odds of the raw probability
      * ``isotonic`` - monotone non-parametric regression
      * ``none``     - identity (the uncalibrated model competes as a candidate)
3. The base pipeline is fitted once on all of TRAIN.
4. All candidates are scored on VALIDATION (Brier, log loss, ROC-AUC, PR-AUC, ECE); the method is
   chosen by the configured metric (default Brier, lower is better) with a parsimony margin: methods are
   considered in configured order (none < sigmoid < isotonic) and a more complex one only wins if it
   improves the metric by more than ``min_improvement`` (noise-level gains do not justify complexity).

No function here accepts test data.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

import numpy as np
import pandas as pd
from sklearn.base import clone
from sklearn.isotonic import IsotonicRegression
from sklearn.linear_model import LogisticRegression
from sklearn.model_selection import cross_val_predict

from ml.pipelines.evaluation import cv_splitter, probability_metrics

METHODS = ("none", "sigmoid", "isotonic")
SELECT_BY = ("brier", "log_loss")
_EPS = 1e-6


def _logit(p: np.ndarray) -> np.ndarray:
    p = np.clip(np.asarray(p, dtype=float), _EPS, 1 - _EPS)
    return np.log(p / (1 - p))


class IdentityCalibrator:
    method = "none"

    def fit(self, p, y):
        return self

    def transform(self, p):
        return np.clip(np.asarray(p, dtype=float), 0.0, 1.0)

    def parameters(self) -> dict:
        return {}


class SigmoidCalibrator:
    """Platt scaling: q = sigmoid(a * logit(p) + b), fitted with (almost) unregularised logistic regression."""
    method = "sigmoid"

    def fit(self, p, y):
        self.lr_ = LogisticRegression(C=1e6, solver="lbfgs", max_iter=1000)
        self.lr_.fit(_logit(p).reshape(-1, 1), np.asarray(y))
        return self

    def transform(self, p):
        return self.lr_.predict_proba(_logit(p).reshape(-1, 1))[:, 1]

    def parameters(self) -> dict:
        return {"a": float(self.lr_.coef_[0, 0]), "b": float(self.lr_.intercept_[0])}


class IsotonicCalibrator:
    method = "isotonic"

    def fit(self, p, y):
        self.iso_ = IsotonicRegression(y_min=0.0, y_max=1.0, out_of_bounds="clip")
        self.iso_.fit(np.asarray(p, dtype=float), np.asarray(y))
        return self

    def transform(self, p):
        return self.iso_.predict(np.asarray(p, dtype=float))

    def parameters(self) -> dict:
        return {"x_thresholds": self.iso_.X_thresholds_.tolist(), "y_thresholds": self.iso_.y_thresholds_.tolist()}


def make_calibrator(method: str):
    if method == "none":
        return IdentityCalibrator()
    if method == "sigmoid":
        return SigmoidCalibrator()
    if method == "isotonic":
        return IsotonicCalibrator()
    raise ValueError(f"Unknown calibration method '{method}'. Choose from {METHODS}.")


class CalibratedModel:
    """Fitted base pipeline + fitted calibrator. Accepts raw customer records (the pipeline coerces them)."""

    classes_ = np.array([0, 1])

    def __init__(self, base, calibrator, method: str):
        self.base = base
        self.calibrator = calibrator
        self.method = method

    def predict_proba(self, X) -> np.ndarray:
        q = np.clip(self.calibrator.transform(self.base.predict_proba(X)[:, 1]), 0.0, 1.0)
        return np.column_stack([1 - q, q])

    def calibration_parameters(self) -> dict:
        return {"method": self.method, **self.calibrator.parameters()}


def out_of_fold_probabilities(fitted_base, X_train: pd.DataFrame, y_train: pd.Series, n_splits: int,
                              seed: int) -> np.ndarray:
    """TRAIN out-of-fold P(churn) of the full pipeline (re-fitted per fold)."""
    return cross_val_predict(clone(fitted_base), X_train, y_train, cv=cv_splitter(n_splits, seed),
                             method="predict_proba", n_jobs=1)[:, 1]


def fit_calibrated_candidates(fitted_base, X_train: pd.DataFrame, y_train: pd.Series, methods: list[str],
                              n_splits: int, seed: int) -> dict[str, CalibratedModel]:
    """One CalibratedModel per method. ``fitted_base`` must already be fitted on TRAIN only."""
    oof = out_of_fold_probabilities(fitted_base, X_train, y_train, n_splits, seed)
    return {m: CalibratedModel(fitted_base, make_calibrator(m).fit(oof, y_train), m) for m in methods}


def reliability_table(y_true, p, n_bins: int = 10) -> tuple[list[dict], float]:
    """Equal-width reliability bins and the expected calibration error (ECE)."""
    y, p = np.asarray(y_true), np.asarray(p, dtype=float)
    idx = np.minimum((p * n_bins).astype(int), n_bins - 1)
    rows, ece = [], 0.0
    for b in range(n_bins):
        m = idx == b
        if not m.any():
            continue
        rows.append({"bin": f"{b / n_bins:.1f}-{(b + 1) / n_bins:.1f}", "n": int(m.sum()),
                     "mean_predicted": float(p[m].mean()), "observed_rate": float(y[m].mean())})
        ece += m.mean() * abs(p[m].mean() - y[m].mean())
    return rows, float(ece)


@dataclass
class CalibrationResult:
    method: str
    select_by: str
    reason: str
    candidates: dict[str, dict]             # method -> validation metrics (+ ece)
    reliability: dict[str, list[dict]]      # method -> reliability bins (validation)
    parameters: dict[str, Any]              # fitted parameters of the SELECTED calibrator
    model: CalibratedModel = field(repr=False, default=None)

    def to_dict(self) -> dict:
        return {"method": self.method, "select_by": self.select_by, "reason": self.reason,
                "candidates": self.candidates, "reliability": self.reliability,
                "parameters": self.parameters}


def calibrate_and_select(
    fitted_base, X_train: pd.DataFrame, y_train: pd.Series, X_val: pd.DataFrame, y_val: pd.Series,
    cal_cfg: dict, seed: int,
) -> CalibrationResult:
    """Fit all configured calibrators on TRAIN, evaluate on VALIDATION, select by ``cal_cfg['select_by']``."""
    select_by = cal_cfg["select_by"]
    if select_by not in SELECT_BY:
        raise ValueError(f"calibration.select_by must be one of {SELECT_BY}, got '{select_by}'.")
    methods = list(cal_cfg["methods"])
    models = fit_calibrated_candidates(fitted_base, X_train, y_train, methods, cal_cfg["cv_folds"], seed)
    metrics: dict[str, dict] = {}
    reliability: dict[str, list[dict]] = {}
    for m, model in models.items():
        p = model.predict_proba(X_val)[:, 1]
        rows, ece = reliability_table(y_val, p, cal_cfg.get("reliability_bins", 10))
        metrics[m] = {**probability_metrics(y_val, p), "ece": ece}
        reliability[m] = rows
    # Parsimony: walk the methods in configured order (simplest first); a later (more complex) method only
    # replaces the incumbent if it is better by more than `min_improvement` - sub-noise gains are ignored.
    margin = float(cal_cfg.get("min_improvement", 0.0))
    best = methods[0]
    for m in methods[1:]:
        if metrics[m][select_by] < metrics[best][select_by] - margin:
            best = m
    ref = metrics.get("none")
    reason = (f"Validation {select_by} {metrics[best][select_by]:.4f}"
              + (f" vs {ref[select_by]:.4f} uncalibrated" if ref and best != "none" else "")
              + f"; a more complex method must improve {select_by} by > {margin:g} to be preferred.")
    return CalibrationResult(best, select_by, reason, metrics, reliability,
                             models[best].calibration_parameters(), models[best])
