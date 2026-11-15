"""Business value segments (Low / Medium / High / Premium).

These are BUSINESS value tiers over a billing or CLV metric. They are unrelated to the Phase 5 ML behavioural clusters.
Thresholds are configurable (quantile or absolute) and always returned with the result.
"""
from __future__ import annotations

import numpy as np
import pandas as pd

from ..analytics.config import SEGMENT_LABELS, ClvConfig
from .calculator import mean_or_none, sum_or_none

UNASSIGNED = "Unassigned"


def metric_column(cfg: ClvConfig) -> str:
    return "billing" if cfg.seg_metric == "observed_billing" else "estimated_clv"


def thresholds(values: pd.Series, cfg: ClvConfig) -> list[float] | None:
    v = values.dropna()
    if v.empty:
        return None
    if cfg.seg_method == "absolute":
        return [float(x) for x in cfg.absolute]
    return [float(np.quantile(v, q)) for q in cfg.quantiles]


def assign(values: pd.Series, cfg: ClvConfig) -> tuple[pd.Series, list[float] | None]:
    t = thresholds(values, cfg)
    seg = pd.Series(UNASSIGNED, index=values.index, dtype="object")
    if t is None:
        return seg, None
    ok = values.notna()
    v = values[ok]
    seg.loc[ok] = np.select([v < t[0], v < t[1], v < t[2]], SEGMENT_LABELS[:3], default=SEGMENT_LABELS[3])
    return seg, t


def segment_table(df: pd.DataFrame, segment: pd.Series) -> list[dict]:
    rows = []
    total_n = max(len(df), 1)
    billing_total = float(df["billing"].dropna().sum())
    for label in (*SEGMENT_LABELS, UNASSIGNED):
        part = df[segment == label]
        if label == UNASSIGNED and part.empty:
            continue
        known = part["churned"].dropna()
        bsum = sum_or_none(part["billing"])
        rows.append({
            "segment": label, "customers": int(len(part)), "customer_share": len(part) / total_n,
            "observed_billing_total": bsum,
            "observed_billing_share": None if bsum is None or billing_total == 0 else bsum / billing_total,
            "avg_observed_billing": mean_or_none(part["billing"]),
            "avg_estimated_clv": mean_or_none(part["estimated_clv"]),
            "monthly_recurring_total": sum_or_none(part["monthly"]),
            "churned_customers": int((known == True).sum()),    # noqa: E712
            "churn_rate": None if known.empty else float((known == True).mean()),   # noqa: E712
            "churn_known_customers": int(len(known)),
        })
    return rows
