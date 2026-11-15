"""Leakage-safe preprocessing.

Everything that *learns* from data (imputer, scaler, encoder, quantile edges) lives inside
one sklearn Pipeline so that it is fitted on training rows only, including inside every
cross-validation fold. Stateless coercion is also inside the pipeline so a saved model
accepts raw customer records.
"""
from __future__ import annotations

from dataclasses import dataclass, field

import numpy as np
import pandas as pd
from pandas.api.types import is_numeric_dtype
from sklearn.base import BaseEstimator, TransformerMixin
from sklearn.compose import ColumnTransformer
from sklearn.impute import SimpleImputer
from sklearn.pipeline import Pipeline
from sklearn.preprocessing import OneHotEncoder, StandardScaler

from ml.pipelines.feature_engineering import FeatureEngineer
from ml.pipelines.ingestion import DatasetSpec
from ml.pipelines.profiling import column_diagnostics, missing_mask, resolve_columns
from ml.pipelines.validation import encode_target


@dataclass
class FeaturePlan:
    numeric: list[str] = field(default_factory=list)
    categorical: list[str] = field(default_factory=list)
    dropped: dict[str, str] = field(default_factory=dict)  # column -> reason

    @property
    def features(self) -> list[str]:
        return self.numeric + self.categorical


def plan_features(df: pd.DataFrame, spec: DatasetSpec, cfg: dict) -> FeaturePlan:
    roles = resolve_columns(df, spec, cfg)
    diag = column_diagnostics(df, roles, cfg)
    drop: dict[str, str] = dict(roles.excluded)
    for reason, cols in diag.items():
        for c in cols:
            drop.setdefault(c, reason)
    max_missing = cfg["limits"]["max_column_missing_fraction"]
    for c in roles.numeric + roles.categorical:
        if c not in drop and float(missing_mask(df[c]).mean()) > max_missing:
            drop[c] = "high_missing"
    return FeaturePlan(
        numeric=[c for c in roles.numeric if c not in drop],
        categorical=[c for c in roles.categorical if c not in drop],
        dropped=drop,
    )


def prepare_xy(df: pd.DataFrame, spec: DatasetSpec, plan: FeaturePlan):
    """Raw feature frame X, binary target y (1 = positive class) and ids; unlabeled rows removed."""
    y_all = encode_target(df[spec.target], spec.positive_class)
    keep = y_all.notna()
    X = df.loc[keep, plan.features].reset_index(drop=True)
    y = y_all[keep].astype(int).reset_index(drop=True)
    ids = df.loc[keep, spec.id_column].reset_index(drop=True) if spec.id_column else None
    return X, y, ids


class FrameCoercer(BaseEstimator, TransformerMixin):
    """Stateless type coercion applied identically at train and inference time."""

    def __init__(self, numeric: list[str] | None = None, categorical: list[str] | None = None):
        self.numeric = numeric
        self.categorical = categorical

    def fit(self, X, y=None):
        return self

    def transform(self, X: pd.DataFrame) -> pd.DataFrame:
        out = X.copy()
        for c in self.numeric or []:
            if c not in out.columns:  # unknown at inference -> missing -> imputed
                out[c] = np.nan
            out[c] = pd.to_numeric(out[c], errors="coerce").replace([np.inf, -np.inf], np.nan)
        for c in self.categorical or []:
            if c not in out.columns:
                out[c] = np.nan
            out[c] = (
                out[c]
                .map(lambda v: np.nan if pd.isna(v) or str(v).strip() == "" else str(v).strip())
                .astype(object)
            )
        return out


# Module-level selectors (not lambdas) so fitted pipelines can be pickled.
def select_numeric(df: pd.DataFrame) -> list[str]:
    return [c for c in df.columns if is_numeric_dtype(df[c])]


def select_categorical(df: pd.DataFrame) -> list[str]:
    return [c for c in df.columns if not is_numeric_dtype(df[c])]


def build_preprocessor() -> ColumnTransformer:
    numeric = Pipeline([
        ("impute", SimpleImputer(strategy="median")),
        ("scale", StandardScaler()),
    ])
    categorical = Pipeline([
        ("impute", SimpleImputer(strategy="most_frequent")),
        ("onehot", OneHotEncoder(handle_unknown="ignore", sparse_output=False)),
    ])
    return ColumnTransformer(
        [("num", numeric, select_numeric), ("cat", categorical, select_categorical)],
        remainder="drop",
    )


def build_pipeline(plan: FeaturePlan, estimator, features_cfg: dict) -> Pipeline:
    """coerce -> engineer features -> impute/scale/encode -> estimator."""
    return Pipeline([
        ("coerce", FrameCoercer(plan.numeric, plan.categorical)),
        ("features", FeatureEngineer(features_cfg)),
        ("preprocess", build_preprocessor()),
        ("model", estimator),
    ])
