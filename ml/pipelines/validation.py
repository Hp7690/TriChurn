"""Validation, split into two clearly separated stages.

* ``validate_dataset``       - DATASET VALIDATION. Structural / schema checks on the raw, full dataset.
                               Descriptive only: it never runs a target-informed screen and its output
                               never selects features or models.
* ``validate_training_data`` - TRAINING VALIDATION. Everything that can influence an ML decision
                               (target-informed leakage screening, feature-drop decisions) runs here and
                               must be given the TRAIN split only. Validation/test rows never reach it.

Hard errors reject the dataset; warnings are reported and handled.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import TYPE_CHECKING

import numpy as np
import pandas as pd
from pandas.api.types import is_datetime64_any_dtype, is_numeric_dtype, is_timedelta64_dtype
from sklearn.metrics import roc_auc_score

from ml.errors import ValidationError
from ml.pipelines.ingestion import DatasetSpec
from ml.pipelines.profiling import (
    column_diagnostics,
    missing_mask,
    resolve_columns,
)

if TYPE_CHECKING:  # avoid a runtime import cycle (preprocessing imports encode_target from here)
    from ml.pipelines.preprocessing import FeaturePlan


@dataclass
class Issue:
    severity: str  # "error" | "warning"
    code: str
    message: str
    column: str | None = None


@dataclass
class ValidationReport:
    issues: list[Issue] = field(default_factory=list)

    @property
    def errors(self) -> list[Issue]:
        return [i for i in self.issues if i.severity == "error"]

    @property
    def warnings(self) -> list[Issue]:
        return [i for i in self.issues if i.severity == "warning"]

    @property
    def ok(self) -> bool:
        return not self.errors

    def add(self, severity: str, code: str, message: str, column: str | None = None) -> None:
        self.issues.append(Issue(severity, code, message, column))

    def raise_if_invalid(self) -> None:
        if not self.ok:
            raise ValidationError(self)

    def to_dict(self) -> dict:
        return {
            "ok": self.ok,
            "errors": [vars(i) for i in self.errors],
            "warnings": [vars(i) for i in self.warnings],
        }


def encode_target(s: pd.Series, positive_class) -> pd.Series:
    """1 where the value equals the positive class, 0 otherwise; NaN/blank stay NaN."""
    valid = ~missing_mask(s)
    out = pd.Series(np.nan, index=s.index, dtype="float64")
    if is_numeric_dtype(s):
        try:
            hit = s.astype("float64") == float(positive_class)
        except (TypeError, ValueError):
            hit = pd.Series(False, index=s.index)
    else:
        hit = s.astype("string").str.strip().eq(str(positive_class).strip()).fillna(False)
    out[valid] = hit[valid].astype(bool).astype("float64")
    return out


def find_leakage_suspects(
    df: pd.DataFrame, y: pd.Series, feature_cols: list[str], numeric_cols: list[str],
    target_name: str, cfg: dict,
) -> list[tuple[str, str]]:
    """Heuristic screen for columns that (almost) reproduce the target. Suspects only.

    Target-informed: ``df``/``y`` must be the TRAIN split only (see ``validate_training_data``).
    """
    lk = cfg["leakage"]
    suspects: list[tuple[str, str]] = []
    valid = y.notna()
    yv = y[valid].astype(int)
    n = len(yv)
    tname = target_name.lower()
    for col in feature_cols:
        if len(tname) >= lk["name_min_length"] and tname in col.lower():
            suspects.append((col, f"column name contains the target name '{target_name}'"))
            continue
        s = df.loc[valid, col]
        m = ~missing_mask(s)
        if m.sum() < 2:
            continue
        sv, yy = s[m], yv[m]
        nunique = sv.nunique()
        if nunique < 2:
            continue
        if nunique <= min(lk["max_cardinality"], max(2, lk["max_cardinality_ratio"] * n)):
            g = yy.groupby(sv.astype(str)).agg(["sum", "count"])
            pred_pos = g["sum"] / g["count"] > 0.5
            tp = g.loc[pred_pos, "sum"].sum()
            fn = g.loc[~pred_pos, "sum"].sum()
            fp = (g.loc[pred_pos, "count"] - g.loc[pred_pos, "sum"]).sum()
            tn = (g.loc[~pred_pos, "count"] - g.loc[~pred_pos, "sum"]).sum()
            if (tp + fn) and (tn + fp):
                bal = 0.5 * (tp / (tp + fn) + tn / (tn + fp))
                if bal >= lk["min_balanced_accuracy"]:
                    suspects.append(
                        (col, f"its values almost perfectly determine the target (balanced acc {bal:.3f})")
                    )
                    continue
        if col in numeric_cols:
            xv = pd.to_numeric(sv, errors="coerce")
            ok = xv.notna()
            if ok.sum() > 2 and xv[ok].nunique() > 1 and yy[ok].nunique() == 2:
                auc = roc_auc_score(yy[ok], xv[ok])
                auc = max(auc, 1 - auc)
                if auc >= lk["min_single_feature_auc"]:
                    suspects.append((col, f"on its own it separates the classes with ROC-AUC {auc:.3f}"))
    return suspects


def validate_dataset(df: pd.DataFrame, spec: DatasetSpec, cfg: dict) -> ValidationReport:
    """DATASET VALIDATION: structural/schema checks on the raw dataset.

    Safe to run on the full dataset because nothing here is target-informed or influences feature
    or model decisions (target-class counts only gate whether a stratified split is feasible).
    Never raises; use report.raise_if_invalid().
    """
    lim = cfg["limits"]
    rep = ValidationReport()

    # --- structural ---
    if df is None or df.shape[0] == 0 or df.shape[1] == 0:
        rep.add("error", "EMPTY_DATASET", "The dataset has no rows or no columns.")
        return rep
    if spec.target not in df.columns:
        rep.add("error", "MISSING_TARGET", f"Target column '{spec.target}' is not in the dataset.")
        return rep
    declared = [c for c in [spec.id_column, *spec.numerical, *spec.categorical, *spec.exclude] if c]
    absent = [c for c in declared if c not in df.columns]
    if absent:
        rep.add("error", "MISSING_COLUMNS", f"Selected columns not found in the data: {absent}.")
        return rep
    if df.shape[0] < lim["min_rows"]:
        rep.add("error", "TOO_FEW_ROWS",
                f"Only {df.shape[0]} rows; at least {lim['min_rows']} are required.")

    # --- target ---
    target = df[spec.target]
    tmiss = missing_mask(target)
    if tmiss.all():
        rep.add("error", "NULL_TARGET", "The target column is completely empty.", spec.target)
        return rep
    if tmiss.any():
        rep.add("warning", "TARGET_PARTIAL_NULL",
                f"{int(tmiss.sum())} rows have no target value and will be excluded.", spec.target)
    y = encode_target(target, spec.positive_class)
    n_pos, n_neg = int((y == 1).sum()), int((y == 0).sum())
    if n_pos == 0 or n_neg == 0:
        rep.add("error", "ONE_CLASS_TARGET",
                f"The target has a single class after treating '{spec.positive_class}' as positive "
                f"(positives={n_pos}, negatives={n_neg}). Check the positive-class selection.",
                spec.target)
        return rep
    if min(n_pos, n_neg) < lim["min_minority_samples"]:
        rep.add("error", "TOO_FEW_MINORITY_SAMPLES",
                f"The minority class has only {min(n_pos, n_neg)} rows; at least "
                f"{lim['min_minority_samples']} are needed for reliable cross-validation.", spec.target)
    n_classes = target[~tmiss].astype(str).str.strip().nunique()
    if n_classes > 2:
        rep.add("warning", "MULTICLASS_TARGET",
                f"The target has {n_classes} distinct values; everything except "
                f"'{spec.positive_class}' is treated as negative.", spec.target)

    # --- identifiers ---
    if spec.id_column:
        ids = df[spec.id_column]
        imiss = missing_mask(ids)
        if imiss.any():
            rep.add("warning", "MISSING_IDS", f"{int(imiss.sum())} rows have no customer ID.",
                    spec.id_column)
        dup = int(ids[~imiss].duplicated().sum())
        if dup:
            rep.add("error", "DUPLICATE_IDS",
                    f"{dup} duplicate customer IDs found. Each customer must appear once.",
                    spec.id_column)

    # --- columns & types ---
    roles = resolve_columns(df, spec, cfg)
    feature_cols = roles.numeric + roles.categorical
    if not feature_cols:
        rep.add("error", "NO_FEATURES", "No usable feature columns after excluding target/ID.")
        return rep

    for col in feature_cols:
        s = df[col]
        if is_datetime64_any_dtype(s) or is_timedelta64_dtype(s):
            rep.add("error", "UNSUPPORTED_TYPE",
                    f"Column '{col}' is a date/time type; convert it to numbers or exclude it.", col)
            continue
        if s.dtype == object:
            sample = s.dropna().head(1000)
            if any(isinstance(v, (list, dict, set, tuple)) for v in sample):
                rep.add("error", "UNSUPPORTED_TYPE",
                        f"Column '{col}' holds nested values (lists/dicts); exclude it.", col)

    if any(i.code == "UNSUPPORTED_TYPE" for i in rep.errors):
        return rep  # later checks assume hashable scalar values

    for col in roles.numeric:
        s = df[col]
        if is_numeric_dtype(s):
            parsed = s.astype("float64")
            nonblank = int(parsed.notna().sum())
            unparsable = 0
        else:
            blank = missing_mask(s)
            parsed = pd.to_numeric(s.where(~blank), errors="coerce")
            nonblank = int((~blank).sum())
            unparsable = int(parsed.isna().sum() - blank.sum())
        if nonblank and unparsable / nonblank > lim["max_unparsable_numeric_fraction"]:
            rep.add("error", "INVALID_NUMERIC_VALUES",
                    f"Numeric column '{col}' has {unparsable} non-numeric values "
                    f"({unparsable / nonblank:.0%}).", col)
        elif unparsable:
            rep.add("warning", "INVALID_NUMERIC_VALUES",
                    f"Numeric column '{col}': {unparsable} non-numeric values treated as missing.", col)
        finite = parsed[np.isfinite(parsed)] if len(parsed) else parsed
        n_inf = int(np.isinf(parsed.dropna()).sum())
        if n_inf:
            rep.add("warning", "INFINITE_VALUES",
                    f"Numeric column '{col}' has {n_inf} infinite values treated as missing.", col)
        if len(finite) and float(finite.abs().max()) > lim["max_abs_numeric_value"]:
            rep.add("error", "EXTREME_VALUES",
                    f"Numeric column '{col}' contains values beyond ±{lim['max_abs_numeric_value']:g}; "
                    f"please check units or exclude the column.", col)

    # --- missingness / structure (descriptive; no drop decision is made here) ---
    diag = column_diagnostics(df, roles, cfg)
    for col in diag["all_null"]:
        rep.add("warning", "ALL_NULL_COLUMN", f"Column '{col}' is empty in the raw data.", col)
    for col in feature_cols:
        n_miss = int(missing_mask(df[col]).sum())
        if 0 < n_miss and col not in diag["all_null"]:
            rep.add("warning", "MISSING_VALUES",
                    f"Column '{col}' has {n_miss} missing values (handled using training data only).", col)
    cells = df.shape[0] * len(feature_cols)
    overall = sum(int(missing_mask(df[c]).sum()) for c in feature_cols) / max(cells, 1)
    if overall > lim["max_overall_missing_fraction"]:
        rep.add("error", "EXCESSIVE_MISSINGNESS",
                f"{overall:.0%} of feature values are missing (limit {lim['max_overall_missing_fraction']:.0%}).")

    dup_rows = int(df.duplicated().sum())
    if dup_rows:
        rep.add("warning", "DUPLICATE_ROWS", f"{dup_rows} fully duplicated rows found.")
    return rep


_DROP_CODES = {"all_null": "all-null", "constant": "constant", "id_like": "identifier-like",
               "high_missing": "too many missing values"}


def validate_training_data(
    train_df: pd.DataFrame, spec: DatasetSpec, cfg: dict, plan: FeaturePlan
) -> ValidationReport:
    """TRAINING VALIDATION: target-informed checks. ``train_df`` MUST be the TRAIN split only.

    * reports every feature the (train-only) plan dropped, and why;
    * runs the target-informed leakage screen over the features the plan kept.
    Validation/test rows are never accepted here, so they cannot influence these decisions.
    """
    rep = ValidationReport()
    for col, reason in plan.dropped.items():
        if reason in _DROP_CODES:
            rep.add("warning", "FEATURE_DROPPED",
                    f"Column '{col}' is {_DROP_CODES[reason]} in the training data and is dropped.", col)
    y = encode_target(train_df[spec.target], spec.positive_class)
    for col, why in find_leakage_suspects(
        train_df, y, plan.features, plan.numeric, spec.target, cfg
    ):
        rep.add("error", "POSSIBLE_TARGET_LEAKAGE",
                f"Column '{col}' may leak the target: {why}. Exclude it or confirm it is known "
                f"before the churn event.", col)
    return rep
