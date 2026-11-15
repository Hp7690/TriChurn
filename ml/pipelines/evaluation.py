"""Metrics and leakage-safe stratified cross-validation."""
from __future__ import annotations

import numpy as np
from sklearn.base import clone
from sklearn.metrics import (
    accuracy_score,
    average_precision_score,
    brier_score_loss,
    confusion_matrix,
    f1_score,
    log_loss,
    make_scorer,
    precision_score,
    recall_score,
    roc_auc_score,
)
from sklearn.model_selection import StratifiedKFold, cross_validate

METRIC_NAMES = ["accuracy", "precision", "recall", "f1", "roc_auc", "pr_auc"]


def compute_metrics(y_true, y_proba, threshold: float = 0.5) -> dict:
    """Metrics for one set of predictions. Confusion matrix layout: [[TN, FP], [FN, TP]]."""
    y_true = np.asarray(y_true)
    y_proba = np.asarray(y_proba)
    y_pred = (y_proba >= threshold).astype(int)
    tn, fp, fn, tp = confusion_matrix(y_true, y_pred, labels=[0, 1]).ravel()
    return {
        "threshold": float(threshold),
        "accuracy": float(accuracy_score(y_true, y_pred)),
        "precision": float(precision_score(y_true, y_pred, zero_division=0)),
        "recall": float(recall_score(y_true, y_pred, zero_division=0)),
        "f1": float(f1_score(y_true, y_pred, zero_division=0)),
        "roc_auc": float(roc_auc_score(y_true, y_proba)),
        "pr_auc": float(average_precision_score(y_true, y_proba)),
        "confusion_matrix": [[int(tn), int(fp)], [int(fn), int(tp)]],
    }


def cv_splitter(n_splits: int, seed: int) -> StratifiedKFold:
    return StratifiedKFold(n_splits=n_splits, shuffle=True, random_state=seed)


def cross_validate_pipeline(pipeline, X, y, n_splits: int = 5, seed: int = 42, cv=None) -> dict:
    """Stratified CV of a *full* pipeline: every transformer is re-fitted inside each fold.

    Returns mean and standard deviation per metric (default 0.5 decision threshold).
    """
    scoring = {
        "accuracy": "accuracy",
        "precision": make_scorer(precision_score, zero_division=0),
        "recall": make_scorer(recall_score, zero_division=0),
        "f1": make_scorer(f1_score, zero_division=0),
        "roc_auc": "roc_auc",
        "pr_auc": "average_precision",
    }
    res = cross_validate(
        clone(pipeline), X, y,
        cv=cv if cv is not None else cv_splitter(n_splits, seed),
        scoring=scoring, n_jobs=1, error_score="raise",
    )
    return {
        m: {"mean": float(np.mean(res[f"test_{m}"])), "std": float(np.std(res[f"test_{m}"], ddof=1))}
        for m in METRIC_NAMES
    } | {"n_splits": len(res["test_f1"])}


def probability_metrics(y_true, y_proba) -> dict:
    """Threshold-free metrics of predicted probabilities (ranking quality + calibration quality)."""
    y_true = np.asarray(y_true)
    y_proba = np.clip(np.asarray(y_proba, dtype=float), 0.0, 1.0)
    return {
        "roc_auc": float(roc_auc_score(y_true, y_proba)),
        "pr_auc": float(average_precision_score(y_true, y_proba)),
        "brier": float(brier_score_loss(y_true, y_proba)),
        "log_loss": float(log_loss(y_true, y_proba, labels=[0, 1])),
    }
