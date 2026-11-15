"""Phase 2 orchestration: tuning -> comparison -> calibration -> threshold -> LOCK -> test (once) -> save.

    RAW -> split_raw (Phase 1.1) ->
      run_optimization_decisions(train_df, val_df, ...)      <- no test parameter exists
          TRAIN : plan_features, leakage screen, tuning CV, fitting, calibrator fitting
          VAL   : model comparison, calibration comparison, threshold optimisation
          lock_model(...)  -> LockedModel (fingerprinted)
      evaluate_on_test(locked, test_df, spec)                <- first and only place TEST is read
      save_artifact(...)

Everything is reproducible from ``training.yaml`` + ``optimization.yaml`` (seeded CV folds, seeded
parameter sampling, seeded estimators).
"""
from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import pandas as pd

from ml.pipelines.calibration import CalibrationResult, calibrate_and_select
from ml.pipelines.final_evaluation import FinalEvaluation, LockedModel, evaluate_on_test, lock_model
from ml.pipelines.ingestion import DatasetSpec
from ml.pipelines.model_selection import ModelComparison, compare_models, validation_metrics
from ml.pipelines.preprocessing import plan_features, prepare_xy
from ml.pipelines.serialization import ArtifactPaths, build_metadata, save_artifact
from ml.pipelines.thresholding import ThresholdResult, optimize_threshold
from ml.pipelines.training import split_raw
from ml.pipelines.tuning import TuningResult, tune_all
from ml.pipelines.validation import validate_training_data


def resolve_seed(training_cfg: dict, opt_cfg: dict) -> int:
    seed = opt_cfg.get("seed")
    return int(training_cfg["seed"] if seed is None else seed)


@dataclass
class OptimizationDecisions:
    """Everything decided from TRAIN and VALIDATION. Contains no test information."""
    plan: Any
    training_validation: dict
    split_sizes: dict
    tuning: dict[str, TuningResult]
    comparison: ModelComparison
    calibration: CalibrationResult
    threshold: ThresholdResult
    validation_final: dict            # selected calibrated model on VALIDATION at the selected threshold
    locked: LockedModel = field(repr=False, default=None)


def run_optimization_decisions(
    train_df: pd.DataFrame, val_df: pd.DataFrame, spec: DatasetSpec, quality_cfg: dict, training_cfg: dict,
    features_cfg: dict, opt_cfg: dict, models: list[str] | None = None,
) -> OptimizationDecisions:
    """Tune, compare, calibrate, optimise the threshold and lock. This function cannot receive test data."""
    seed = resolve_seed(training_cfg, opt_cfg)
    plan = plan_features(train_df, spec, quality_cfg)                       # TRAIN only
    train_report = validate_training_data(train_df, spec, quality_cfg, plan)  # TRAIN only (leakage screen)
    train_report.raise_if_invalid()
    X_train, y_train, _ = prepare_xy(train_df, spec, plan)
    X_val, y_val, _ = prepare_xy(val_df, spec, plan)                        # train-decided columns only

    tuning = tune_all(X_train, y_train, plan, training_cfg, features_cfg, opt_cfg, seed, models)   # TRAIN
    comparison = compare_models(tuning, X_train, y_train, X_val, y_val, plan, features_cfg,
                                opt_cfg["selection"], opt_cfg["threshold"], seed)   # TRAIN CV + VALIDATION
    chosen = comparison.selected_evaluation
    calibration = calibrate_and_select(chosen.pipeline, X_train, y_train, X_val, y_val,
                                       opt_cfg["calibration"], seed)        # fit TRAIN, compare VALIDATION
    p_val = calibration.model.predict_proba(X_val)[:, 1]
    threshold = optimize_threshold(y_val, p_val, opt_cfg["threshold"])      # VALIDATION only
    locked = lock_model(calibration.model, chosen.name, chosen.imbalance, chosen.params, threshold, plan,
                        seed, X_val)
    return OptimizationDecisions(
        plan=plan, training_validation=train_report.to_dict(),
        split_sizes={"train": len(train_df), "validation": len(val_df)},
        tuning=tuning, comparison=comparison, calibration=calibration, threshold=threshold,
        validation_final=validation_metrics(y_val, p_val, threshold.threshold), locked=locked,
    )


@dataclass
class OptimizationReport:
    decisions: OptimizationDecisions
    final: FinalEvaluation
    split_sizes: dict
    dataset: dict
    artifact: ArtifactPaths | None
    configuration: dict

    def to_dict(self) -> dict:
        d, f = self.decisions, self.final
        return {
            "phase": "2 - model optimization, calibration, thresholding and final evaluation",
            "dataset": self.dataset, "split_sizes": self.split_sizes,
            "configuration": self.configuration,
            "feature_plan": {"numeric": d.plan.numeric, "categorical": d.plan.categorical,
                             "dropped": d.plan.dropped},
            "training_validation": d.training_validation,
            "tuning": {m: t.to_dict() for m, t in d.tuning.items()},
            "model_comparison": d.comparison.to_dict(),
            "calibration": d.calibration.to_dict(),
            "threshold": d.threshold.to_dict(),
            "validation_final": d.validation_final,
            "locked_decisions": d.locked.decisions(),
            "final_test": f.to_dict(),
            "artifact": ({"model": self.artifact.model.name, "metadata": self.artifact.metadata.name,
                          "sha256": self.artifact.sha256} if self.artifact else None),
            "isolation": {
                "test_used_for_tuning": False, "test_used_for_model_selection": False,
                "test_used_for_calibration": False, "test_used_for_threshold": False,
                "test_evaluated_after_lock": True, "test_evaluations": 1,
                "decision_fingerprint": d.locked.fingerprint,
            },
        }


def run_optimization_on_splits(
    train_df: pd.DataFrame, val_df: pd.DataFrame, test_df: pd.DataFrame, spec: DatasetSpec,
    quality_cfg: dict, training_cfg: dict, features_cfg: dict, opt_cfg: dict,
    dataset_info: dict | None = None, models: list[str] | None = None,
    artifact_dir: str | Path | None = None, trained_at: str | None = None,
) -> OptimizationReport:
    """Decisions (TRAIN/VALIDATION) -> lock -> TEST once -> serialize. ``test_df`` is first read after the lock."""
    dec = run_optimization_decisions(train_df, val_df, spec, quality_cfg, training_cfg, features_cfg,
                                     opt_cfg, models)
    final = evaluate_on_test(dec.locked, test_df, spec)   # <- first and only read of the test split
    split_sizes = {**dec.split_sizes, "test": len(test_df)}
    info = dataset_info or {}
    artifact = None
    if artifact_dir is not None:
        chosen = dec.comparison.selected_evaluation
        metadata = build_metadata(
            dec.locked, spec, final, training_cfg=training_cfg, features_cfg=features_cfg, opt_cfg=opt_cfg,
            tuning_summary={"n_candidates": {m: t.n_candidates for m, t in dec.tuning.items()},
                            "primary_metric": opt_cfg["tuning"]["primary_metric"],
                            "n_splits": opt_cfg["tuning"]["cv"]["n_splits"]},
            cv_metrics=chosen.cv,
            validation_metrics={"uncalibrated_at_0.5": chosen.validation,
                                "calibrated_at_selected_threshold": dec.validation_final},
            dataset_info=info, split_sizes=split_sizes, trained_at=trained_at)
        artifact = save_artifact(dec.locked, metadata, artifact_dir, opt_cfg["artifacts"]["name"])
    return OptimizationReport(
        dec, final, split_sizes, info, artifact,
        {"seed": dec.locked.seed, "split": training_cfg["split"], "optimization": opt_cfg},
    )


def run_optimization(
    df: pd.DataFrame, spec: DatasetSpec, quality_cfg: dict, training_cfg: dict, features_cfg: dict,
    opt_cfg: dict, dataset_info: dict | None = None, models: list[str] | None = None,
    artifact_dir: str | Path | None = None, trained_at: str | None = None,
) -> OptimizationReport:
    """Raw frame -> Phase 1.1 split -> full Phase 2 flow."""
    sp = training_cfg["split"]
    raw = split_raw(df, spec, sp["val_size"], sp["test_size"], training_cfg["seed"])
    return run_optimization_on_splits(raw.train, raw.val, raw.test, spec, quality_cfg, training_cfg,
                                      features_cfg, opt_cfg, dataset_info, models, artifact_dir, trained_at)
