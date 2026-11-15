"""Time-indexed revenue schema, validation and forecast-readiness evaluation (NO model is trained here).

Expected fields: period, customer_id, revenue (+ optional product, segment). If real history is missing or too short the
state is FORECAST_BLOCKED_BY_INSUFFICIENT_HISTORY: no model is fitted and no projection is produced.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

import pandas as pd

from ..analytics.config import ForecastConfig

BLOCKED_HISTORY = "FORECAST_BLOCKED_BY_INSUFFICIENT_HISTORY"
BLOCKED_INVALID = "FORECAST_BLOCKED_BY_INVALID_DATA"
BLOCKED_NONE = BLOCKED_HISTORY      # no history at all is the extreme case of insufficient history
READY = "FORECAST_READY"
REQUIRED = ("period", "customer_id", "revenue")
OPTIONAL = ("product", "segment")

SCHEMA = {"required": {"period": "ISO date (YYYY-MM or YYYY-MM-DD)", "customer_id": "string",
                       "revenue": "number >= 0, billed revenue for the period (not profit)"},
          "optional": {"product": "string", "segment": "string"}, "frequency": "M"}


@dataclass
class ReadinessReport:
    state: str
    reasons: list[str] = field(default_factory=list)
    rows_received: int = 0
    rows_valid: int = 0
    invalid_dates: int = 0
    invalid_revenue: int = 0
    negative_revenue: int = 0
    duplicate_rows: int = 0
    distinct_customers: int = 0
    periods_observed: int = 0
    first_period: str | None = None
    last_period: str | None = None
    missing_periods: list[str] = field(default_factory=list)
    missing_period_share: float | None = None
    min_periods_required: int = 0
    seasonality_ready: bool = False
    forecast_executed: bool = False

    def as_dict(self) -> dict[str, Any]:
        return dict(self.__dict__)


def _blocked(state: str, reasons: list[str], cfg: ForecastConfig, **kw: Any) -> tuple[ReadinessReport, None]:
    return ReadinessReport(state=state, reasons=reasons, min_periods_required=cfg.min_periods, **kw), None


def validate(frame: pd.DataFrame | None, cfg: ForecastConfig) -> tuple[ReadinessReport, pd.Series | None]:
    """Return (report, monthly revenue series). The series is only returned when the state is FORECAST_READY."""
    if frame is None or len(frame) == 0:
        return _blocked(BLOCKED_NONE, ["No time-indexed revenue observations were supplied. The Telco snapshot has "
                                       "no historical revenue series."], cfg)
    n = len(frame)
    missing_cols = [c for c in REQUIRED if c not in frame.columns]
    if missing_cols:
        return _blocked(BLOCKED_INVALID, [f"Missing required columns: {missing_cols}"], cfg, rows_received=n)
    df = frame[[c for c in (*REQUIRED, *OPTIONAL) if c in frame.columns]].copy()
    parsed = pd.to_datetime(df["period"], errors="coerce", format="mixed")
    bad_dates = int(parsed.isna().sum())
    rev = pd.to_numeric(df["revenue"], errors="coerce")
    bad_rev = int(rev.isna().sum())
    neg = int((rev < 0).sum())
    df["_p"], df["_r"] = parsed.dt.to_period("M"), rev
    valid = df[parsed.notna() & rev.notna() & (rev >= 0) & df["customer_id"].astype(str).str.strip().ne("")]
    key = ["customer_id", "_p"] + [c for c in OPTIONAL if c in valid.columns and c == "product"]
    dups = int(valid.duplicated(subset=key, keep=False).sum())
    rep_kw = dict(rows_received=n, rows_valid=len(valid), invalid_dates=bad_dates, invalid_revenue=bad_rev,
                  negative_revenue=neg, duplicate_rows=dups)
    reasons = []
    if bad_dates:
        reasons.append(f"{bad_dates} rows have unparseable dates.")
    if bad_rev or neg:
        reasons.append(f"{bad_rev} non-numeric and {neg} negative revenue values.")
    if dups:
        reasons.append(f"{dups} rows share the same customer_id and period (duplicate periods); aggregation would "
                       "double count.")
    if reasons:
        return ReadinessReport(state=BLOCKED_INVALID, reasons=reasons, min_periods_required=cfg.min_periods,
                               **rep_kw), None
    if valid.empty:
        return _blocked(BLOCKED_NONE, ["No valid rows remained after validation."], cfg, **rep_kw)
    monthly = valid.groupby("_p")["_r"].sum().sort_index()
    full = pd.period_range(monthly.index.min(), monthly.index.max(), freq="M")
    missing = [str(p) for p in full.difference(monthly.index)]
    share = len(missing) / len(full)
    base = dict(distinct_customers=int(valid["customer_id"].nunique()), periods_observed=len(monthly),
                first_period=str(full[0]), last_period=str(full[-1]), missing_periods=missing,
                missing_period_share=round(share, 4), min_periods_required=cfg.min_periods,
                seasonality_ready=len(full) >= cfg.min_periods_seasonality, **rep_kw)
    if len(full) < cfg.min_periods:
        return ReadinessReport(state=BLOCKED_HISTORY, reasons=[
            f"{len(full)} monthly periods span the data; at least {cfg.min_periods} are required."], **base), None
    if share > cfg.max_missing_share:
        return ReadinessReport(state=BLOCKED_HISTORY, reasons=[
            f"{share:.0%} of periods are missing; the maximum allowed is {cfg.max_missing_share:.0%}."],
            **base), None
    series = monthly.reindex(full)
    return ReadinessReport(state=READY, reasons=["Validation passed. Missing periods (if any) are NOT imputed: "
                                                  "models must handle gaps explicitly."], **base), series
