"""Clustering features and preprocessing (UNSUPERVISED: the target, model outputs and business outputs never enter).

Feature set (``configs/segmentation.yaml: features``): raw numeric columns plus Phase 1 ``FeatureEngineer`` outputs
(``service_count``, ``contract_risk``: domain priors, not learned from the target). The builder reads ONLY the columns
it needs, so a target column present in the input frame cannot reach the clustering even by accident, and the
configuration validator refuses the dataset's target / id and any forbidden name.
"""
from __future__ import annotations

from collections.abc import Sequence
from typing import Any

import numpy as np
import pandas as pd
from sklearn.base import BaseEstimator, TransformerMixin
from sklearn.impute import SimpleImputer
from sklearn.pipeline import Pipeline
from sklearn.preprocessing import MinMaxScaler, StandardScaler

from ml.errors import SegmentationConfigError, SegmentationInputError
from ml.pipelines.feature_engineering import FeatureEngineer
from ml.pipelines.ingestion import DatasetSpec
from ml.segmentation.schemas import FeatureSetConfig, SegmentationConfig


def validate_feature_set(features: FeatureSetConfig, spec: DatasetSpec) -> None:
    """Refuse the dataset's target / id column and anything on the forbidden list (case-insensitive)."""
    barred = {spec.target.lower(), spec.id_column.lower(), *features.forbidden}
    hit = [f for f in features.all if f.lower() in barred]
    if hit:
        raise SegmentationConfigError(
            f"Clustering features {hit} are not allowed: the target, the id and model/business outputs may not be "
            "used to cluster customers.")


def _role_columns(features_cfg: dict | None) -> list[str]:
    cols: list[str] = []
    for value in ((features_cfg or {}).get("roles") or {}).values():
        cols.extend([] if value is None else [value] if isinstance(value, str) else list(value))
    return cols


class SegmentationFeatureBuilder(BaseEstimator, TransformerMixin):
    """Raw customer frame -> numeric matrix of exactly the configured clustering features (NaN kept for the imputer)."""

    def __init__(self, numeric: Sequence[str] = (), engineered: Sequence[str] = (), features_cfg: dict | None = None):
        self.numeric = numeric
        self.engineered = engineered
        self.features_cfg = features_cfg

    def _used(self, X: pd.DataFrame) -> pd.DataFrame:
        wanted = dict.fromkeys([*self.numeric, *_role_columns(self.features_cfg)])
        return X[[c for c in wanted if c in X.columns]]          # nothing else (e.g. a target column) is passed on

    def fit(self, X: pd.DataFrame, y: Any = None) -> SegmentationFeatureBuilder:
        missing = [c for c in self.numeric if c not in X.columns]
        if missing:
            raise SegmentationInputError(f"Customer data is missing clustering columns {missing}.")
        self.engineer_ = FeatureEngineer(self.features_cfg).fit(self._used(X))
        absent = {f: self.engineer_.skipped_.get(f, "not produced by FeatureEngineer")
                  for f in self.engineered if f not in self.engineer_.created_}
        if absent:
            raise SegmentationInputError(f"Engineered clustering features cannot be built: {absent}.")
        self.feature_names_ = [*self.numeric, *self.engineered]
        return self

    def transform(self, X: pd.DataFrame) -> pd.DataFrame:
        missing = [c for c in self.numeric if c not in X.columns]
        if missing:
            raise SegmentationInputError(f"Customer data is missing clustering columns {missing}.")
        used = self._used(X)
        engineered = self.engineer_.transform(used)
        out = pd.DataFrame(index=X.index)
        for col in self.numeric:
            out[col] = pd.to_numeric(used[col], errors="coerce").replace([np.inf, -np.inf], np.nan)
        for col in self.engineered:
            out[col] = engineered[col]
        return out[self.feature_names_].astype("float64")

    def get_feature_names_out(self, input_features: Any = None) -> np.ndarray:
        return np.asarray(self.feature_names_, dtype=object)


def build_preprocessor(cfg: SegmentationConfig, features_cfg: dict, spec: DatasetSpec) -> Pipeline:
    """Builder -> imputer -> scaler (unfitted). Fit it on TRAIN customers only."""
    validate_feature_set(cfg.features, spec)
    scalers = {"standard": StandardScaler(), "minmax": MinMaxScaler(), "none": "passthrough"}
    return Pipeline([
        ("features", SegmentationFeatureBuilder(cfg.features.numeric, cfg.features.engineered, features_cfg)),
        ("impute", SimpleImputer(strategy=cfg.imputation, keep_empty_features=True)),
        ("scale", scalers[cfg.scaling]),
    ])
