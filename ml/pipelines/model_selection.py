"""Phase 2 - candidate model comparison and selection (TRAIN CV + VALIDATION only).

Each model's best tuned configuration is fitted on TRAIN and scored on VALIDATION. The model is then
chosen by a transparent, configurable composite of CV (TRAIN) and validation scores. No test data is
accepted anywhere in this module.

Fair comparison of threshold-dependent metrics: F1 / recall / precision / accuracy at a fixed 0.5 cut-off
mostly reflect the class-weighting strategy (a class-weighted model shifts every probability upward), not
model quality. So for the composite, each model gets its OWN decision threshold, chosen on its TRAIN
out-of-fold probabilities (same stratified folds as tuning) with the configured threshold objective.
CV-side threshold metrics are computed on those pooled out-of-fold probabilities, validation-side ones apply
that TRAIN-derived threshold to the VALIDATION predictions. The 0.5-threshold numbers stay in the report for
information. (The final threshold is still chosen separately, after calibration, in ``thresholding``.)
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

import pandas as pd
from sklearn.base import clone
from sklearn.model_selection import cross_val_predict

from ml.pipelines.evaluation import compute_metrics, cv_splitter, probability_metrics
from ml.pipelines.preprocessing import FeaturePlan
from ml.pipelines.thresholding import optimize_threshold
from ml.pipelines.tuning import TuningResult, build_candidate_pipeline

SELECTABLE_METRICS = ("pr_auc", "roc_auc", "f1", "recall", "precision", "accuracy")


def validation_metrics(y_true, y_proba, threshold: float = 0.5) -> dict:
    """Threshold-free probability metrics + threshold-dependent metrics (kept separate in the output)."""
    return {
        "probability_metrics": probability_metrics(y_true, y_proba),
        "threshold_metrics": {k: v for k, v in compute_metrics(y_true, y_proba, threshold).items()
                              if k not in ("roc_auc", "pr_auc")},
    }


THRESHOLD_FREE = ("pr_auc", "roc_auc")


def composite_score(cv_scores: dict, val_scores: dict, sel_cfg: dict) -> float:
    """(w_cv * sum_m w_m * CV_m + w_val * sum_m w_m * VAL_m) / (w_cv + w_val); metric weights normalised.

    ``cv_scores`` / ``val_scores`` are flat ``{metric: value}`` dicts."""
    weights = sel_cfg["metric_weights"]
    unknown = set(weights) - set(SELECTABLE_METRICS)
    if unknown:
        raise ValueError(f"Unknown selection metrics {sorted(unknown)}; choose from {SELECTABLE_METRICS}.")
    wsum = sum(weights.values())
    csum = sel_cfg["cv_weight"] + sel_cfg["validation_weight"]
    cv_part = sum(w * cv_scores[m] for m, w in weights.items()) / wsum
    val_part = sum(w * val_scores[m] for m, w in weights.items()) / wsum
    return (sel_cfg["cv_weight"] * cv_part + sel_cfg["validation_weight"] * val_part) / csum


@dataclass
class ModelEvaluation:
    name: str
    imbalance: str
    params: dict[str, Any]
    cv: dict                      # TRAIN cross-validation of the tuned configuration (0.5 cut-off for F1/recall)
    validation: dict              # {"probability_metrics", "threshold_metrics"} at 0.5, uncalibrated
    composite: float
    selection_threshold: float = 0.5          # this model's TRAIN out-of-fold-optimal threshold
    cv_at_selection_threshold: dict = field(default_factory=dict)   # pooled OOF threshold metrics
    validation_at_selection_threshold: dict = field(default_factory=dict)
    baseline_cv: dict | None = None
    baseline_validation: dict | None = None   # informational only: never used to select
    pipeline: Any = field(default=None, repr=False)   # fitted on TRAIN

    def to_dict(self) -> dict:
        return {"name": self.name, "imbalance": self.imbalance, "params": self.params, "cv": self.cv,
                "validation": self.validation, "composite": self.composite,
                "selection_threshold": self.selection_threshold,
                "cv_at_selection_threshold": self.cv_at_selection_threshold,
                "validation_at_selection_threshold": self.validation_at_selection_threshold,
                "baseline_cv": self.baseline_cv, "baseline_validation": self.baseline_validation}


@dataclass
class ModelComparison:
    evaluations: list[ModelEvaluation]
    selected: str
    reason: str
    selection_config: dict

    def get(self, name: str) -> ModelEvaluation:
        return next(e for e in self.evaluations if e.name == name)

    @property
    def selected_evaluation(self) -> ModelEvaluation:
        return self.get(self.selected)

    def to_dict(self) -> dict:
        return {"selected": self.selected, "reason": self.reason, "selection_config": self.selection_config,
                "models": [e.to_dict() for e in self.evaluations]}


def _threshold_scores(y_true, p, thr: float) -> dict:
    m = compute_metrics(y_true, p, thr)
    return {k: m[k] for k in ("accuracy", "precision", "recall", "f1")} | {"threshold": float(thr)}


def compare_models(
    tuning: dict[str, TuningResult], X_train: pd.DataFrame, y_train: pd.Series,
    X_val: pd.DataFrame, y_val: pd.Series, plan: FeaturePlan, features_cfg: dict, sel_cfg: dict,
    threshold_cfg: dict, seed: int,
) -> ModelComparison:
    """Fit each model's best tuned config on TRAIN, score on VALIDATION, pick the best composite."""
    th_cfg = {**threshold_cfg, "override": None}   # a policy override must not distort model comparison
    evals: list[ModelEvaluation] = []
    for name, tr in tuning.items():
        best = tr.best
        pipe = build_candidate_pipeline(name, best.imbalance, best.params, y_train, plan, features_cfg, seed)
        # TRAIN out-of-fold probabilities (same stratified folds as tuning) -> this model's own threshold
        oof = cross_val_predict(clone(pipe), X_train, y_train, cv=cv_splitter(tr.n_splits, seed),
                                method="predict_proba", n_jobs=1)[:, 1]
        thr = optimize_threshold(y_train, oof, th_cfg).threshold
        pipe.fit(X_train, y_train)
        p_val = pipe.predict_proba(X_val)[:, 1]
        val = validation_metrics(y_val, p_val)
        cv_thr = _threshold_scores(y_train, oof, thr)
        val_thr = _threshold_scores(y_val, p_val, thr)
        cv_scores = {m: best.cv[m]["mean"] for m in THRESHOLD_FREE} | {k: v for k, v in cv_thr.items()
                                                                       if k != "threshold"}
        val_scores = val["probability_metrics"] | {k: v for k, v in val_thr.items() if k != "threshold"}
        base_cv = base_val = None
        if tr.baseline is not None:
            b = tr.baseline
            base_cv = b.cv
            bp = build_candidate_pipeline(name, b.imbalance, b.params, y_train, plan, features_cfg, seed)
            bp.fit(X_train, y_train)
            base_val = validation_metrics(y_val, bp.predict_proba(X_val)[:, 1])
        evals.append(ModelEvaluation(
            name, best.imbalance, best.params, best.cv, val, composite_score(cv_scores, val_scores, sel_cfg),
            float(thr), cv_thr, val_thr, base_cv, base_val, pipe))
    winner = max(evals, key=lambda e: e.composite)  # max() keeps the first of equal scores (config order)
    runner = sorted(evals, key=lambda e: -e.composite)
    gap = winner.composite - runner[1].composite if len(runner) > 1 else 0.0
    reason = (f"Highest composite score ({winner.composite:.4f}) of CV-on-TRAIN and VALIDATION metrics "
              f"weighted {sel_cfg['metric_weights']} (F1/recall at each model's own TRAIN out-of-fold-optimal "
              f"threshold, not a fixed 0.5)"
              + (f"; margin over {runner[1].name}: {gap:.4f}." if len(runner) > 1 else "."))
    return ModelComparison(evals, winner.name, reason, dict(sel_cfg))
