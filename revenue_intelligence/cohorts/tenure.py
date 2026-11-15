"""Tenure-based cohorts. Method label: TENURE_BASED_PROXY.

A tenure bucket groups customers by months of tenure at snapshot time. It is NOT an acquisition-month cohort: the data
has no signup date, so there are no calendar retention curves, and the comparison is cross-sectional (survivor bias).
"""
from __future__ import annotations

import numpy as np
import pandas as pd

from ..analytics.config import CohortConfig
from ..clv.calculator import mean_or_none, sum_or_none

METHOD = "TENURE_BASED_PROXY"
UNKNOWN = "Unknown"


def bucket_labels(edges: tuple[int, ...]) -> list[str]:
    labels = [f"{edges[0]}-{edges[1]}"]
    labels += [f"{edges[i] + 1}-{edges[i + 1]}" for i in range(1, len(edges) - 1)]
    labels.append(f"{edges[-1] + 1}+")
    return labels


def assign_buckets(tenure: pd.Series, cfg: CohortConfig) -> pd.Series:
    labels = bucket_labels(cfg.edges)
    uppers = list(cfg.edges[1:])
    ok = tenure.notna()
    out = pd.Series(UNKNOWN, index=tenure.index, dtype="object")
    t = tenure[ok]
    conds = [t <= u for u in uppers]
    out.loc[ok] = np.select(conds, labels[:-1], default=labels[-1])
    return out


def assign_lifecycle(tenure: pd.Series, cfg: CohortConfig) -> pd.Series:
    out = pd.Series(UNKNOWN, index=tenure.index, dtype="object")
    for name, (lo, hi) in cfg.lifecycle.items():
        m = tenure.notna() & (tenure >= lo) & (True if hi is None else (tenure <= hi))
        out[m] = name
    return out


def aggregate(df: pd.DataFrame, group: pd.Series, order: list[str]) -> list[dict]:
    rows, total = [], max(len(df), 1)
    present = [g for g in order if (group == g).any()]
    if (group == UNKNOWN).any():
        present.append(UNKNOWN)
    for g in present:
        part = df[group == g]
        known = part["churned"].dropna()
        rows.append({
            "cohort": g, "customers": int(len(part)), "customer_share": len(part) / total,
            "churned_customers": int((known == True).sum()),    # noqa: E712
            "churn_rate": None if known.empty else float((known == True).mean()),    # noqa: E712
            "avg_monthly_charges": mean_or_none(part["monthly"]),
            "avg_observed_billing": mean_or_none(part["billing"]),
            "avg_estimated_clv": mean_or_none(part["estimated_clv"]),
            "monthly_recurring_total": sum_or_none(part["monthly"]),
            "observed_billing_total": sum_or_none(part["billing"]),
        })
    return rows


UNSUPPORTED = [
    ("acquisition_month_cohorts", "Requires a customer signup/acquisition date."),
    ("calendar_month_retention_curves", "Requires dated activity or billing periods per customer."),
    ("revenue_retention_by_acquisition_month", "Requires dated revenue observations plus signup dates."),
    ("repeat_purchase_cohorts", "Requires purchase/transaction events."),
    ("monthly_revenue_cohort_heatmap", "Requires monthly revenue observations per customer."),
]
