"""Phase 2 - the lock and the one-time final TEST evaluation.

``lock_model`` freezes every decision (model + hyperparameters + calibration + threshold) into a
``LockedModel`` with a content fingerprint computed *before* any test row is read. ``evaluate_on_test`` is
the ONLY function in the project that consumes the test split for Phase 2. It

* refuses to run twice for the same locked model (``TestSetAlreadyEvaluatedError``),
* re-checks the fingerprint before and after scoring (decisions cannot change under the test data),
* never refits, recalibrates or re-thresholds anything.

Probability metrics (threshold-free) and threshold-dependent classification metrics are reported in
separate blocks.
"""
from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass, field
from typing import Any

import numpy as np
import pandas as pd

from ml.errors import TestSetAlreadyEvaluatedError
from ml.pipelines.calibration import CalibratedModel
from ml.pipelines.evaluation import compute_metrics, probability_metrics
from ml.pipelines.ingestion import DatasetSpec
from ml.pipelines.preprocessing import FeaturePlan, prepare_xy
from ml.pipelines.thresholding import ThresholdResult

PROBE_ROWS = 50


def _digest(obj: Any) -> str:
    return hashlib.sha256(json.dumps(obj, sort_keys=True, default=str).encode()).hexdigest()


@dataclass
class LockedModel:
    """Everything decided before the test split is read."""
    model: CalibratedModel = field(repr=False)
    model_name: str
    imbalance: str
    params: dict[str, Any]
    calibration_method: str
    calibration_parameters: dict[str, Any]
    threshold: ThresholdResult
    plan: FeaturePlan
    seed: int
    probe: pd.DataFrame = field(repr=False)       # a few VALIDATION rows used to fingerprint behaviour
    fingerprint: str = ""
    test_consumed: bool = False

    def current_fingerprint(self) -> str:
        probs = np.round(self.model.predict_proba(self.probe)[:, 1], 10).tolist()
        return _digest({
            "model": self.model_name, "imbalance": self.imbalance, "params": self.params,
            "calibration": self.calibration_method, "calibration_parameters": self.calibration_parameters,
            "threshold": self.threshold.threshold, "features": self.plan.features, "probe_probs": probs,
        })

    def decisions(self) -> dict:
        return {"model": self.model_name, "imbalance": self.imbalance, "params": self.params,
                "calibration_method": self.calibration_method,
                "calibration_parameters": self.calibration_parameters,
                "threshold": self.threshold.threshold, "fingerprint": self.fingerprint}


def lock_model(model: CalibratedModel, model_name: str, imbalance: str, params: dict, threshold: ThresholdResult,
               plan: FeaturePlan, seed: int, X_val: pd.DataFrame) -> LockedModel:
    """Freeze the final decisions. ``X_val`` only supplies a few rows to fingerprint model behaviour."""
    locked = LockedModel(model, model_name, imbalance, params, model.method, model.calibration_parameters(),
                         threshold, plan, seed, X_val.head(PROBE_ROWS).copy())
    locked.fingerprint = locked.current_fingerprint()
    return locked


@dataclass
class FinalEvaluation:
    """Final TEST report. Probability metrics and threshold-dependent metrics are kept apart."""
    n_test: int
    positive_rate: float
    threshold: float
    probability_metrics: dict      # threshold-free: ROC-AUC, PR-AUC, Brier, log loss
    threshold_metrics: dict        # at `threshold`: accuracy, precision, recall, F1, confusion matrix
    lock_fingerprint: str

    def to_dict(self) -> dict:
        return {"n_test": self.n_test, "positive_rate": self.positive_rate,
                "selected_threshold": self.threshold, "probability_metrics": self.probability_metrics,
                "threshold_metrics": self.threshold_metrics, "lock_fingerprint": self.lock_fingerprint,
                "note": ("probability_metrics are threshold-free; threshold_metrics apply the validation-"
                         "selected threshold. The test split influenced no decision.")}


def evaluate_on_test(locked: LockedModel, test_df: pd.DataFrame, spec: DatasetSpec) -> FinalEvaluation:
    """Score the locked model on TEST exactly once. Nothing is fitted, calibrated or tuned here."""
    if locked.test_consumed:
        raise TestSetAlreadyEvaluatedError(
            "The test split was already evaluated for this model. It is reserved for a single final "
            "evaluation; a second look would turn it into a validation set.")
    if locked.current_fingerprint() != locked.fingerprint:
        raise RuntimeError("Locked decisions changed after locking; refusing to read the test split.")
    locked.test_consumed = True
    X_test, y_test, _ = prepare_xy(test_df, spec, locked.plan)
    p = locked.model.predict_proba(X_test)[:, 1]
    thr = locked.threshold.threshold
    threshold_block = {k: v for k, v in compute_metrics(y_test, p, thr).items()
                       if k not in ("roc_auc", "pr_auc")}
    if locked.current_fingerprint() != locked.fingerprint:  # defence in depth
        raise RuntimeError("Locked decisions changed during test evaluation.")
    return FinalEvaluation(len(y_test), float(np.mean(y_test)), float(thr), probability_metrics(y_test, p),
                           threshold_block, locked.fingerprint)
