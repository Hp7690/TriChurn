"""Dataset profiling and the (explicitly defined) Data Quality Score."""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

import pandas as pd
from pandas.api.types import is_bool_dtype, is_numeric_dtype

from ml.pipelines.ingestion import DatasetSpec


def missing_mask(s: pd.Series) -> pd.Series:
    """True where a value is null OR a blank string (e.g. Telco's ' ' TotalCharges)."""
    mask = s.isna()
    if is_bool_dtype(s) or is_numeric_dtype(s):
        return mask
    blank = s.astype("string").str.strip().eq("").fillna(False).astype(bool)
    return mask | blank


@dataclass
class ColumnRoles:
    numeric: list[str] = field(default_factory=list)
    categorical: list[str] = field(default_factory=list)
    excluded: dict[str, str] = field(default_factory=dict)  # column -> reason


def _is_numeric_like(s: pd.Series, min_parse_fraction: float) -> bool:
    if is_bool_dtype(s):
        return False
    if is_numeric_dtype(s):
        return True
    nonmissing = s[~missing_mask(s)]
    if nonmissing.empty:
        return False
    return bool(pd.to_numeric(nonmissing, errors="coerce").notna().mean() >= min_parse_fraction)


def resolve_columns(df: pd.DataFrame, spec: DatasetSpec, cfg: dict) -> ColumnRoles:
    """Split columns into numeric/categorical features. Declared lists win; the rest is inferred."""
    roles = ColumnRoles()
    skip = {spec.target: "target"}
    if spec.id_column:
        skip[spec.id_column] = "id_column"
    for c in spec.exclude:
        skip.setdefault(c, "user_excluded")
    roles.excluded.update({c: r for c, r in skip.items() if c in df.columns})

    min_parse = cfg["numeric_inference_min_parse_fraction"]
    for col in df.columns:
        if col in skip:
            continue
        if col in spec.numerical:
            roles.numeric.append(col)
        elif col in spec.categorical:
            roles.categorical.append(col)
        elif _is_numeric_like(df[col], min_parse):
            roles.numeric.append(col)
        else:
            roles.categorical.append(col)
    return roles


def column_diagnostics(df: pd.DataFrame, roles: ColumnRoles, cfg: dict) -> dict[str, list[str]]:
    """Find all-null, constant and ID-like feature columns."""
    idl = cfg["id_like"]
    out: dict[str, list[str]] = {"all_null": [], "constant": [], "id_like": []}
    for col in roles.numeric + roles.categorical:
        s = df[col]
        nonmissing = s[~missing_mask(s)]
        if nonmissing.empty:
            out["all_null"].append(col)
            continue
        n_unique = nonmissing.nunique()
        if n_unique <= 1:
            out["constant"].append(col)
            continue
        if len(nonmissing) < idl["min_rows_to_judge"]:
            continue
        ratio = n_unique / len(nonmissing)
        if col in roles.categorical and ratio >= idl["categorical_unique_ratio"]:
            out["id_like"].append(col)
        elif col in roles.numeric and ratio >= idl["integer_unique_ratio"]:
            parsed = pd.to_numeric(nonmissing, errors="coerce").dropna()
            if len(parsed) and bool((parsed % 1 == 0).all()):
                out["id_like"].append(col)
    return out


def profile_dataset(df: pd.DataFrame, spec: DatasetSpec, cfg: dict) -> dict[str, Any]:
    """Observed facts about the dataset (nothing estimated)."""
    roles = resolve_columns(df, spec, cfg)
    diag = column_diagnostics(df, roles, cfg)
    n_rows, n_cols = df.shape

    miss = {c: int(missing_mask(df[c]).sum()) for c in df.columns}
    feature_cols = roles.numeric + roles.categorical
    feat_cells = max(n_rows * len(feature_cols), 1)
    feat_missing = sum(miss[c] for c in feature_cols)

    dup_rows = int(df.duplicated().sum())
    dup_ids = 0
    if spec.id_column and spec.id_column in df.columns:
        ids = df[spec.id_column]
        dup_ids = int(ids[~missing_mask(ids)].duplicated().sum())

    target_dist: dict[str, Any] = {}
    imbalance: dict[str, Any] = {}
    if spec.target in df.columns:
        t = df[spec.target]
        tvalid = t[~missing_mask(t)].astype(str).str.strip()
        counts = tvalid.value_counts()
        target_dist = {
            "counts": {str(k): int(v) for k, v in counts.items()},
            "missing": int(missing_mask(t).sum()),
        }
        pos = tvalid.eq(str(spec.positive_class).strip()).sum()
        total = len(tvalid)
        if total:
            pos_rate = pos / total
            minority = min(pos_rate, 1 - pos_rate)
            imbalance = {
                "positive_rate": float(pos_rate),
                "minority_share": float(minority),
                "imbalance_ratio": float((1 - minority) / minority) if minority > 0 else None,
            }

    return {
        "rows": int(n_rows),
        "columns": int(n_cols),
        "missing_per_column": miss,
        "missing_pct_per_column": {c: round(100 * v / max(n_rows, 1), 3) for c, v in miss.items()},
        "overall_missing_fraction": float(feat_missing / feat_cells),
        "duplicate_rows": dup_rows,
        "duplicate_ids": dup_ids,
        "constant_columns": diag["constant"],
        "all_null_columns": diag["all_null"],
        "id_like_columns": diag["id_like"],
        "numeric_columns": roles.numeric,
        "categorical_columns": roles.categorical,
        "unique_counts": {c: int(df[c].nunique(dropna=True)) for c in df.columns},
        "target_distribution": target_dist,
        "imbalance": imbalance,
    }


def quality_score(profile: dict[str, Any], hard_failed: bool, cfg: dict) -> dict[str, Any]:
    """Data Quality Score (0-100): 100 minus five capped, documented penalties.

    Observed inputs only. Datasets that fail hard validation are 'Rejected', not scored.
    """
    if hard_failed:
        return {"score": None, "band": "Rejected", "components": {}}
    sc = cfg["score"]
    caps = sc["caps"]
    n_rows = max(profile["rows"], 1)
    n_feat = max(len(profile["numeric_columns"]) + len(profile["categorical_columns"]), 1)

    def frac(x: float, full_at: float) -> float:
        return float(min(1.0, max(0.0, x / full_at)))

    flagged = len(profile["constant_columns"]) + len(profile["id_like_columns"]) + len(
        profile["all_null_columns"]
    )
    minority = profile["imbalance"].get("minority_share", 0.5)
    imb_pen = 0.0
    if minority < sc["imbalance_threshold"]:
        imb_pen = caps["imbalance"] * frac(
            sc["imbalance_threshold"] - minority,
            sc["imbalance_threshold"] - sc["imbalance_full_penalty_share"],
        )
    size_pen = 0.0
    if n_rows < sc["small_sample_rows"]:
        size_pen = caps["sample_size"] * (1 - n_rows / sc["small_sample_rows"])

    components = {
        "missing": caps["missing"]
        * frac(profile["overall_missing_fraction"], sc["missing_full_penalty_fraction"]),
        "duplicates": caps["duplicates"]
        * frac(
            (profile["duplicate_rows"] + profile["duplicate_ids"]) / n_rows,
            sc["duplicates_full_penalty_fraction"],
        ),
        "structure": caps["structure"] * frac(flagged / n_feat, sc["structure_full_penalty_fraction"]),
        "imbalance": imb_pen,
        "sample_size": size_pen,
    }
    components = {k: round(float(v), 2) for k, v in components.items()}
    score = round(100 - sum(components.values()), 1)
    b = cfg["bands"]
    band = (
        "Excellent" if score >= b["excellent"]
        else "Good" if score >= b["good"]
        else "Needs Attention" if score >= b["needs_attention"]
        else "Poor"
    )
    return {"score": score, "band": band, "components": components}


__all__ = [
    "ColumnRoles", "missing_mask", "resolve_columns", "column_diagnostics",
    "profile_dataset", "quality_score",
]
