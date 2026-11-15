"""Framework for TRUE acquisition cohorts. Activates only when real signup dates and dated revenue are supplied.

Nothing is fabricated: with no ``signup_date`` / ``period`` data the result is BLOCKED_BY_MISSING_DATA.
"""
from __future__ import annotations

from typing import Any

import pandas as pd


def acquisition_cohorts(customers: pd.DataFrame | None, revenue: pd.DataFrame | None) -> dict[str, Any]:
    """customers: customer_id, signup_date. revenue: customer_id, period, revenue (>0 means active that month)."""
    if customers is None or revenue is None or customers.empty or revenue.empty:
        return {"status": "BLOCKED_BY_MISSING_DATA", "reason": "No signup dates and dated revenue were supplied.",
                "cohorts": []}
    need_c, need_r = {"customer_id", "signup_date"}, {"customer_id", "period", "revenue"}
    if not need_c <= set(customers.columns) or not need_r <= set(revenue.columns):
        return {"status": "BLOCKED_BY_MISSING_DATA", "reason": f"Required columns: {sorted(need_c)} and "
                f"{sorted(need_r)}.", "cohorts": []}
    c = customers[["customer_id", "signup_date"]].copy()
    c["signup_date"] = pd.to_datetime(c["signup_date"], errors="coerce")
    r = revenue[["customer_id", "period", "revenue"]].copy()
    r["period"] = pd.to_datetime(r["period"], errors="coerce")
    r["revenue"] = pd.to_numeric(r["revenue"], errors="coerce")
    bad = int(c["signup_date"].isna().sum() + r["period"].isna().sum() + r["revenue"].isna().sum())
    c, r = c.dropna(), r.dropna()
    if c.empty or r.empty:
        return {"status": "BLOCKED_BY_MISSING_DATA", "reason": "No valid signup dates or dated revenue remained.",
                "invalid_values_dropped": bad, "cohorts": []}
    c = c.drop_duplicates("customer_id")
    c["cohort"] = c["signup_date"].dt.to_period("M")
    r["month"] = r["period"].dt.to_period("M")
    m = r.merge(c[["customer_id", "cohort"]], on="customer_id", how="inner")
    m["age"] = (m["month"].dt.year - m["cohort"].dt.year) * 12 + (m["month"].dt.month - m["cohort"].dt.month)
    m = m[(m["age"] >= 0) & (m["revenue"] > 0)]
    sizes = c.groupby("cohort")["customer_id"].nunique()
    rows = []
    for cohort, size in sizes.items():
        part = m[m["cohort"] == cohort]
        active = part.groupby("age")["customer_id"].nunique()
        rev = part.groupby("age")["revenue"].sum()
        rows.append({"cohort": str(cohort), "customers": int(size),
                     "retention_by_age": {int(a): float(active[a] / size) for a in active.index},
                     "revenue_by_age": {int(a): float(rev[a]) for a in rev.index}})
    return {"status": "ACTUAL", "reason": None, "invalid_values_dropped": bad, "cohorts": rows}
