"""Phase 3 - encoded-feature -> source-feature mapping, aggregation, global importance and drivers.

Mapping rule (derived from the FITTED ColumnTransformer, nothing hard-coded):
  * ``ColumnTransformer.transformers_`` lists, per branch, the resolved input columns (the selector callables
    are already evaluated) and the fitted sub-pipeline, in the same order as ``get_feature_names_out()``.
  * If a branch ends in a OneHotEncoder, each input column ``c`` owns ``len(categories_[i])`` consecutive encoded
    columns (label ``c=<category>``); any other branch (imputer/scaler) maps one encoded column to its input column.
  * The result is cross-checked against ``get_feature_names_out()`` (width and name prefix); any disagreement
    raises instead of guessing.
Aggregation rule: the SHAP value of a source feature is the SUM of the SHAP values of its encoded columns
(SHAP values are additive, so the sum is that feature's exact joint contribution and the total is unchanged).
Source features are the columns that enter the encoder: the caller's raw columns plus engineered columns
(``tenure_group``, ``contract_risk``...), which stay separate features and are flagged ``is_engineered``.
"""
from __future__ import annotations

from dataclasses import dataclass

import numpy as np
from sklearn.compose import ColumnTransformer
from sklearn.pipeline import Pipeline
from sklearn.preprocessing import OneHotEncoder

from ml.errors import ExplainabilityError
from ml.explainability.schemas import (
    DECREASES_CHURN,
    INCREASES_CHURN,
    NEUTRAL,
    FeatureContribution,
    GlobalImportanceItem,
    LocalExplanation,
)

_ROUND = 12   # sort keys are rounded so float noise cannot reorder ties


@dataclass(frozen=True)
class FeatureMap:
    """Encoded model column i belongs to source feature ``source_of[i]``."""
    encoded_names: list[str]      # as produced by the fitted preprocessor, e.g. "cat__Contract_One year"
    encoded_labels: list[str]     # readable: "Contract=One year" or "tenure"
    source_of: list[str]          # source feature of each encoded column
    sources: list[str]            # unique source features, in model-input order
    groups: dict[str, np.ndarray]  # source feature -> indices of its encoded columns

    def aggregate(self, shap_matrix: np.ndarray) -> np.ndarray:
        """(n_rows, n_encoded) -> (n_rows, n_sources): signed sum per source feature, columns follow ``sources``."""
        sv = np.asarray(shap_matrix, dtype=float)
        if sv.ndim != 2 or sv.shape[1] != len(self.source_of):
            raise ExplainabilityError(
                f"SHAP matrix has shape {sv.shape}; expected (n_rows, {len(self.source_of)}).")
        return np.column_stack([sv[:, self.groups[s]].sum(axis=1) for s in self.sources])


def build_feature_map(preprocess: ColumnTransformer) -> FeatureMap:
    """Derive the encoded -> source mapping from a FITTED ColumnTransformer."""
    names = [str(n) for n in preprocess.get_feature_names_out()]
    labels: list[str] = []
    source_of: list[str] = []
    for branch, trans, cols in preprocess.transformers_:
        if branch == "remainder" or trans == "drop":
            continue
        cols = [str(c) for c in cols]
        final = trans.steps[-1][1] if isinstance(trans, Pipeline) else trans
        if isinstance(final, OneHotEncoder):
            n_cats = sum(len(c) for c in final.categories_)
            if final.drop_idx_ is not None or len(final.get_feature_names_out()) != n_cats:
                raise ExplainabilityError("Unsupported OneHotEncoder configuration (drop / infrequent categories).")
            for col, cats in zip(cols, final.categories_, strict=True):
                labels += [f"{col}={cat}" for cat in cats]
                source_of += [col] * len(cats)
        else:
            labels += cols
            source_of += cols
    if len(source_of) != len(names):
        raise ExplainabilityError(
            f"Feature mapping covers {len(source_of)} columns but the preprocessor outputs {len(names)}.")
    # name-level cross-check: "<branch>__<source>" or "<branch>__<source>_<category>"
    for name, src in zip(names, source_of, strict=True):
        body = name.split("__", 1)[1] if "__" in name else name
        if body != src and not body.startswith(f"{src}_"):
            raise ExplainabilityError(f"Encoded column '{name}' does not belong to mapped source feature '{src}'.")
    sources = list(dict.fromkeys(source_of))
    groups = {s: np.array([i for i, x in enumerate(source_of) if x == s], dtype=int) for s in sources}
    return FeatureMap(names, labels, source_of, sources, groups)


# --------------------------------------------------------------------------------------------- direction
def direction_for(shap_value: float, epsilon: float) -> str:
    if shap_value > epsilon:
        return INCREASES_CHURN
    if shap_value < -epsilon:
        return DECREASES_CHURN
    return NEUTRAL


# ----------------------------------------------------------------------------------------- global importance
def global_importance(feature_map: FeatureMap, shap_matrix: np.ndarray) -> list[GlobalImportanceItem]:
    """mean(|source-level SHAP|) per source feature (aggregate first, then abs, then mean over rows).

    Sorted by importance descending, then source-feature name ascending; ranks are 1..n in that order."""
    agg = feature_map.aggregate(shap_matrix)
    if agg.shape[0] == 0:
        raise ExplainabilityError("Cannot compute global importance from zero rows.")
    mean_abs = np.abs(agg).mean(axis=0)
    order = sorted(range(len(feature_map.sources)),
                   key=lambda i: (-round(float(mean_abs[i]), _ROUND), feature_map.sources[i]))
    return [GlobalImportanceItem(feature_map.sources[i], float(mean_abs[i]), rank)
            for rank, i in enumerate(order, start=1)]


# ----------------------------------------------------------------------------------------------- drivers
def _check_n(n: int) -> None:
    if not isinstance(n, int) or isinstance(n, bool) or n < 1:
        raise ValueError("n must be a positive integer.")


def top_positive_drivers(explanation: LocalExplanation, n: int = 5) -> list[FeatureContribution]:
    """Features with a POSITIVE log-odds contribution (toward a higher model churn score), largest first.

    Ties are broken by feature name. Neutral and negative features are never returned."""
    _check_n(n)
    pos = [f for f in explanation.features if f.direction == INCREASES_CHURN]
    return sorted(pos, key=lambda f: (-round(f.shap_value, _ROUND), f.source_feature))[:n]


def top_negative_drivers(explanation: LocalExplanation, n: int = 5) -> list[FeatureContribution]:
    """Features with a NEGATIVE log-odds contribution (toward a lower model churn score), most negative first."""
    _check_n(n)
    neg = [f for f in explanation.features if f.direction == DECREASES_CHURN]
    return sorted(neg, key=lambda f: (round(f.shap_value, _ROUND), f.source_feature))[:n]
