"""Phase 1 training flow (test-isolated).

    RAW -> dataset validation (structural) -> profile (descriptive) -> stratified split
        -> TRAIN only: feature planning -> training validation / leakage screen
                       -> CV -> fit
        -> VALIDATION: model comparison / evaluation
        -> TEST: created by the split, then never read in Phase 1 (only its length is reported)

Nothing target-informed and nothing that learns from data ever sees validation/test rows. The test
split is reserved for the single final evaluation after tuning, calibration and threshold selection
(Phase 2).
"""
from __future__ import annotations

import time
from dataclasses import dataclass, field
from typing import Any

import pandas as pd
from sklearn.ensemble import RandomForestClassifier
from sklearn.linear_model import LogisticRegression
from sklearn.model_selection import train_test_split
from xgboost import XGBClassifier

from ml.pipelines.evaluation import compute_metrics, cross_validate_pipeline
from ml.pipelines.ingestion import DatasetSpec
from ml.pipelines.preprocessing import FeaturePlan, build_pipeline, plan_features, prepare_xy
from ml.pipelines.profiling import profile_dataset, quality_score
from ml.pipelines.validation import (
    ValidationReport,
    encode_target,
    validate_dataset,
    validate_training_data,
)

MODEL_NAMES = ["logistic_regression", "random_forest", "xgboost"]


@dataclass
class SplitData:
    X_train: pd.DataFrame
    X_val: pd.DataFrame
    X_test: pd.DataFrame
    y_train: pd.Series
    y_val: pd.Series
    y_test: pd.Series


def split_data(X: pd.DataFrame, y: pd.Series, val_size: float, test_size: float, seed: int) -> SplitData:
    """Stratified train/validation/test split. Done BEFORE any transformer is fitted."""
    X_tmp, X_test, y_tmp, y_test = train_test_split(
        X, y, test_size=test_size, stratify=y, random_state=seed
    )
    rel_val = val_size / (1 - test_size)
    X_train, X_val, y_train, y_val = train_test_split(
        X_tmp, y_tmp, test_size=rel_val, stratify=y_tmp, random_state=seed
    )
    return SplitData(X_train, X_val, X_test, y_train, y_val, y_test)


@dataclass
class RawSplit:
    """Row-level split of the raw frame (all columns kept; nothing fitted or planned yet)."""
    train: pd.DataFrame
    val: pd.DataFrame
    test: pd.DataFrame


def split_raw(df: pd.DataFrame, spec: DatasetSpec, val_size: float, test_size: float,
              seed: int) -> RawSplit:
    """Stratified train/validation/test split of the RAW frame, done before any feature planning.

    Rows without a target value are removed (label presence only). Stratification necessarily reads
    the labels to assign rows to partitions; it makes no feature or model decision. The partition is
    identical to splitting (X, y) after feature selection with the same seed and row order.
    """
    y_all = encode_target(df[spec.target], spec.positive_class)
    keep = y_all.notna()
    labeled = df.loc[keep].reset_index(drop=True)
    y = y_all[keep].astype(int).reset_index(drop=True)
    s = split_data(labeled, y, val_size, test_size, seed)
    return RawSplit(s.X_train, s.X_val, s.X_test)


def make_estimator(name: str, imbalance: str, y_train: pd.Series, cfg: dict, seed: int):
    """imbalance: 'none' | 'balanced' (class weights / scale_pos_weight). No resampling."""
    if name not in MODEL_NAMES:
        raise ValueError(f"Unknown model '{name}'. Choose from {MODEL_NAMES}.")
    params = dict(cfg["models"][name])
    balanced = imbalance == "balanced"
    if name == "logistic_regression":
        return LogisticRegression(class_weight="balanced" if balanced else None,
                                  random_state=seed, **params)
    if name == "random_forest":
        return RandomForestClassifier(class_weight="balanced_subsample" if balanced else None,
                                      random_state=seed, n_jobs=-1, **params)
    if name == "xgboost":
        pos = int((y_train == 1).sum())
        spw = (len(y_train) - pos) / max(pos, 1) if balanced else 1.0
        return XGBClassifier(scale_pos_weight=spw, eval_metric="logloss", tree_method="hist",
                             random_state=seed, n_jobs=-1, **params)
    raise AssertionError("unreachable")


@dataclass
class ModelResult:
    name: str
    imbalance: str
    cv: dict
    validation: dict
    fit_seconds: float
    selected_imbalance: bool = False
    pipeline: Any = field(default=None, repr=False)

    def to_dict(self) -> dict:
        return {"name": self.name, "imbalance": self.imbalance, "cv": self.cv,
                "validation": self.validation, "fit_seconds": round(self.fit_seconds, 2),
                "selected_imbalance": self.selected_imbalance}


def train_models(
    X_train: pd.DataFrame, y_train: pd.Series, X_val: pd.DataFrame, y_val: pd.Series,
    plan: FeaturePlan, training_cfg: dict, features_cfg: dict,
    models: list[str] | None = None,
) -> list[ModelResult]:
    """CV on train, fit on train, score on validation. (No test data is accepted here.)

    For each model every imbalance strategy is run; the strategy with the higher CV PR-AUC
    (training data only) is flagged selected_imbalance.
    """
    seed = training_cfg["seed"]
    results: list[ModelResult] = []
    for name in models or MODEL_NAMES:
        group: list[ModelResult] = []
        for imb in training_cfg["imbalance"]["candidates"]:
            t0 = time.perf_counter()
            pipe = build_pipeline(plan, make_estimator(name, imb, y_train, training_cfg, seed),
                                  features_cfg)
            cv = cross_validate_pipeline(pipe, X_train, y_train,
                                         n_splits=training_cfg["cv"]["n_splits"], seed=seed)
            pipe.fit(X_train, y_train)
            val = compute_metrics(y_val, pipe.predict_proba(X_val)[:, 1])
            group.append(ModelResult(name, imb, cv, val, time.perf_counter() - t0, pipeline=pipe))
        max(group, key=lambda r: r.cv["pr_auc"]["mean"]).selected_imbalance = True
        results.extend(group)
    return results


@dataclass
class TrainingReport:
    dataset: dict
    profile: dict
    quality: dict
    validation: dict            # DATASET validation: structural, raw/full data
    training_validation: dict   # TRAINING validation: target-informed, TRAIN split only
    feature_plan: dict
    engineered_features: dict
    split_sizes: dict
    results: list[ModelResult]

    def to_dict(self) -> dict:
        return {
            "dataset": self.dataset, "profile": self.profile, "quality": self.quality,
            "validation": self.validation, "training_validation": self.training_validation,
            "feature_plan": self.feature_plan,
            "engineered_features": self.engineered_features, "split_sizes": self.split_sizes,
            "results": [r.to_dict() for r in self.results],
            "notes": ("Metrics are at a 0.5 threshold. Validation metrics are on the validation "
                      "split; the test split is untouched in Phase 1. Flow: structural validation "
                      "(raw) -> split -> feature planning, leakage screening, CV and fitting on TRAIN "
                      "only. 'profile' and 'quality' are descriptive statistics of the raw dataset and "
                      "feed no model or feature decision."),
        }


def run_training(
    df: pd.DataFrame, spec: DatasetSpec, quality_cfg: dict, training_cfg: dict, features_cfg: dict,
    dataset_info: dict | None = None, models: list[str] | None = None,
) -> TrainingReport:
    """Structural validation -> profile -> split -> TRAIN-only planning/screening -> train.

    Raises ValidationError if the dataset (structural) or the training data (leakage) is rejected.
    """
    report = validate_dataset(df, spec, quality_cfg)  # DATASET validation: structural, raw data
    report.raise_if_invalid()
    profile = profile_dataset(df, spec, quality_cfg)  # descriptive only; feeds no decision
    quality = quality_score(profile, hard_failed=False, cfg=quality_cfg)
    sp = training_cfg["split"]
    raw = split_raw(df, spec, sp["val_size"], sp["test_size"], training_cfg["seed"])
    return run_training_on_splits(
        raw.train, raw.val, raw.test, spec, quality_cfg, training_cfg, features_cfg,
        dataset_info=dataset_info, models=models,
        structural=report, profile=profile, quality=quality,
    )


def run_training_on_splits(
    train_df: pd.DataFrame, val_df: pd.DataFrame, test_df: pd.DataFrame, spec: DatasetSpec,
    quality_cfg: dict, training_cfg: dict, features_cfg: dict,
    dataset_info: dict | None = None, models: list[str] | None = None,
    structural: ValidationReport | None = None, profile: dict | None = None,
    quality: dict | None = None,
) -> TrainingReport:
    """Everything after the split. ``test_df`` is accepted but only ``len(test_df)`` is read.

    TRAIN only : plan_features, training validation (leakage screen), CV, fitting.
    VALIDATION : scoring the fitted pipelines.
    TEST       : never read (reserved for the final evaluation in a later phase).
    """
    plan = plan_features(train_df, spec, quality_cfg)               # TRAIN only
    train_report = validate_training_data(train_df, spec, quality_cfg, plan)  # TRAIN only
    train_report.raise_if_invalid()
    X_train, y_train, _ = prepare_xy(train_df, spec, plan)
    X_val, y_val, _ = prepare_xy(val_df, spec, plan)  # applies the train-decided column list only
    results = train_models(X_train, y_train, X_val, y_val, plan, training_cfg, features_cfg, models)
    fe = results[0].pipeline.named_steps["features"]
    return TrainingReport(
        dataset=dataset_info or {},
        profile=profile or {}, quality=quality or {},
        validation=(structural or ValidationReport()).to_dict(),
        training_validation=train_report.to_dict(),
        feature_plan={"numeric": plan.numeric, "categorical": plan.categorical,
                      "dropped": plan.dropped},
        engineered_features={"created": fe.created_, "skipped": fe.skipped_},
        split_sizes={"train": len(train_df), "validation": len(val_df), "test": len(test_df)},
        results=results,
    )
