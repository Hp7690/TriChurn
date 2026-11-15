"""Safe CSV loading, canonicalisation and data-quality accounting for the customer snapshot.

Nothing is invented: invalid numbers become NaN (unavailable), never 0; duplicates are dropped (first kept) and counted;
inconsistent rows are FLAGGED, never silently corrected.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import numpy as np
import pandas as pd

from ..errors import RevenueDataUnavailableError, RevenueInputError
from .config import DataConfig, QualityConfig

REQUIRED = ("customerID", "tenure", "MonthlyCharges")
OPTIONAL = ("TotalCharges", "Contract", "Churn", "InternetService", "OnlineSecurity", "OnlineBackup",
            "DeviceProtection", "TechSupport", "StreamingTV", "StreamingMovies", "PhoneService")


@dataclass
class QualityReport:
    rows_read: int = 0
    rows_used: int = 0
    duplicate_ids_dropped: int = 0
    missing_customer_id: int = 0
    invalid_tenure: int = 0
    invalid_monthly_charges: int = 0
    missing_total_charges: int = 0
    invalid_total_charges: int = 0
    zero_tenure_rows: int = 0
    inconsistent_total_vs_monthly: int = 0
    churn_unknown: int = 0
    missing_columns: list[str] = field(default_factory=list)
    notes: list[str] = field(default_factory=list)

    def as_dict(self) -> dict[str, Any]:
        return dict(self.__dict__)


def resolve_csv_path(configured: str | None, candidates: tuple[str, ...], root: Path) -> Path:
    """Resolve the CSV inside ``root`` only (prevents path traversal); raises DataUnavailable if none exists."""
    root = root.resolve()
    options = [configured] if configured else list(candidates)
    for opt in options:
        if not opt:
            continue
        p = Path(opt)
        p = (p if p.is_absolute() else root / p).resolve()
        if configured is None and root not in p.parents and p != root:
            continue
        if configured is not None and root not in p.parents:
            raise RevenueInputError("data file must be located inside the project directory")
        if p.is_file():
            return p
    raise RevenueDataUnavailableError("No customer CSV was found. Set TRICHURN_REVENUE_DATA_CSV or place the Telco "
                                      "snapshot at one of the configured candidate paths.")


def read_csv_safely(path: Path, cfg: DataConfig) -> pd.DataFrame:
    if path.suffix.lower() != ".csv":
        raise RevenueInputError("only .csv files are accepted")
    if path.stat().st_size > cfg.max_file_bytes:
        raise RevenueInputError("data file exceeds the configured size limit")
    try:
        df = pd.read_csv(path, dtype=str, keep_default_na=False, nrows=cfg.max_rows + 1, encoding="utf-8")
    except (UnicodeDecodeError, pd.errors.ParserError, pd.errors.EmptyDataError) as exc:
        raise RevenueInputError("data file could not be parsed as UTF-8 CSV") from exc
    if len(df) > cfg.max_rows:
        raise RevenueInputError("data file exceeds the configured row limit")
    return df


def _num(series: pd.Series) -> pd.Series:
    text = series.astype(str).str.strip()
    out = pd.to_numeric(text.mask(text.isin(["", "nan", "None"])), errors="coerce")
    return out.replace([np.inf, -np.inf], np.nan)


def prepare(raw: pd.DataFrame, quality: QualityConfig, prob_col: str | None = None,
            prob_provenance: str = "UNKNOWN") -> tuple[pd.DataFrame, QualityReport]:
    """Canonical frame with numeric columns ``tenure``, ``monthly``, ``billing`` (NaN = unavailable) and flags."""
    rep = QualityReport(rows_read=len(raw))
    missing = [c for c in REQUIRED if c not in raw.columns]
    if missing:
        raise RevenueInputError(f"required columns missing: {missing}")
    rep.missing_columns = [c for c in OPTIONAL if c not in raw.columns]
    df = raw.copy()
    df["customerID"] = df["customerID"].astype(str).str.strip()
    blank = df["customerID"].isin(["", "nan", "None"])
    rep.missing_customer_id = int(blank.sum())
    df = df[~blank]
    dup = df["customerID"].duplicated(keep="first")
    rep.duplicate_ids_dropped = int(dup.sum())
    df = df[~dup].reset_index(drop=True)

    df["tenure_n"] = _num(df["tenure"])
    bad_t = df["tenure_n"].isna() | (df["tenure_n"] < 0) | (df["tenure_n"] % 1 != 0)
    rep.invalid_tenure = int(bad_t.sum())
    df.loc[bad_t, "tenure_n"] = np.nan
    df["monthly"] = _num(df["MonthlyCharges"])
    bad_m = df["monthly"].isna() | (df["monthly"] < 0)
    rep.invalid_monthly_charges = int(bad_m.sum())
    df.loc[bad_m, "monthly"] = np.nan

    if "TotalCharges" in df.columns:
        stripped = df["TotalCharges"].astype(str).str.strip()
        was_blank = stripped.isin(["", "nan", "None"])
        total = _num(df["TotalCharges"])
        neg = total < 0
        rep.missing_total_charges = int(was_blank.sum())
        rep.invalid_total_charges = int(((total.isna() & ~was_blank) | neg).sum())
        total[neg] = np.nan
        df["billing"] = total
    else:
        df["billing"] = np.nan
        rep.notes.append("TotalCharges column absent: observed billing is UNAVAILABLE.")
    rep.zero_tenure_rows = int((df["tenure_n"] == 0).sum())

    expected = df["monthly"] * df["tenure_n"]
    ratio = df["billing"] / expected.where(expected > 0)
    df["billing_inconsistent"] = ((ratio < quality.ratio_min) | (ratio > quality.ratio_max)).fillna(False)
    rep.inconsistent_total_vs_monthly = int(df["billing_inconsistent"].sum())

    if "Churn" in df.columns:
        c = df["Churn"].astype(str).str.strip().str.lower()
        df["churned"] = c.map({"yes": True, "no": False})
        rep.churn_unknown = int(df["churned"].isna().sum())
    else:
        df["churned"] = np.nan
        rep.churn_unknown = len(df)
        rep.notes.append("Churn column absent: churn-based metrics are UNAVAILABLE.")
    df["churned"] = df["churned"].astype("object")

    for col in ("Contract", "InternetService", *[c for c in OPTIONAL if c.startswith(("Online", "Device", "Tech",
                                                                                    "Streaming"))]):
        if col in df.columns:
            df[col] = df[col].astype(str).str.strip()
    df["probability"] = np.nan
    df.attrs["probability_provenance"] = "UNKNOWN"
    if prob_col and prob_col in raw.columns:
        p = _num(df[prob_col])
        p[(p < 0) | (p > 1)] = np.nan
        df["probability"] = p
        df.attrs["probability_provenance"] = prob_provenance
    rep.rows_used = len(df)
    return df, rep


def usable_probabilities(df: pd.DataFrame) -> pd.Series | None:
    """Probabilities may be used for weighting ONLY with VALIDATED_OUT_OF_SAMPLE provenance (never in-sample)."""
    if df.attrs.get("probability_provenance") != "VALIDATED_OUT_OF_SAMPLE":
        return None
    return df["probability"] if df["probability"].notna().any() else None


def frame_from_rows(rows: list[dict[str, Any]]) -> pd.DataFrame:
    """Build a DataFrame from records for embedding and integration use."""
    return pd.DataFrame(rows)
