"""Revenue exposure analytics. Three distinct, separately labelled views:

1. HISTORICAL context (ACTUAL): billing / recurring charges of customers ALREADY labelled Churn = Yes. Already lost,
   NOT at risk, never presented as a prediction.
2. RULE_FLAGGED exposure (PROXY): recurring charges of ACTIVE customers matching >= N screening indicators.
   Unweighted, not a probability, not expected loss.
3. PROBABILITY_WEIGHTED exposure (ESTIMATED): sum(MonthlyCharges x p) over active customers, only with a churn
   probability of VALIDATED_OUT_OF_SAMPLE provenance. Otherwise UNAVAILABLE with the reason.
"""
from __future__ import annotations

import numpy as np
import pandas as pd

from ..analytics.config import RiskConfig
from ..analytics.dataset import usable_probabilities
from ..clv.calculator import sum_or_none


def active_mask(df: pd.DataFrame) -> pd.Series:
    return df["churned"] == False    # noqa: E712 - unknown churn is NOT treated as active


def add_risk_columns(df: pd.DataFrame, cfg: RiskConfig) -> pd.DataFrame:
    out = df.copy()
    ind = pd.DataFrame(index=out.index)
    contract = out["Contract"] if "Contract" in out.columns else pd.Series(np.nan, index=out.index)
    if cfg.month_to_month:
        ind["month_to_month"] = contract == "Month-to-month"
    if cfg.max_tenure_months > 0:
        ind["short_tenure"] = out["tenure_n"].notna() & (out["tenure_n"] <= cfg.max_tenure_months)
    if cfg.internet_without_tech_support and "InternetService" in out.columns and "TechSupport" in out.columns:
        ind["internet_without_tech_support"] = (out["InternetService"].isin(["DSL", "Fiber optic"])
                                                & (out["TechSupport"] == "No"))
    out["risk_indicator_count"] = ind.sum(axis=1) if not ind.empty else 0
    out["risk_indicator_names"] = ind.apply(lambda r: [c for c in ind.columns if r[c]], axis=1) \
        if not ind.empty else [[] for _ in range(len(out))]
    can_flag = out["churned"].isin([True, False]).any()
    out["rule_flagged"] = active_mask(out) & (out["risk_indicator_count"] >= cfg.min_indicators) & can_flag
    p = usable_probabilities(out)
    out["expected_exposure"] = (out["monthly"] * p).where(active_mask(out)) if p is not None else np.nan
    return out


def probability_status(df: pd.DataFrame) -> tuple[bool, str]:
    prov = df.attrs.get("probability_provenance", "UNKNOWN")
    if df["probability"].notna().sum() == 0:
        return False, ("No churn-probability column is configured. Probability-weighted exposure needs validated "
                       "out-of-sample probabilities; none were supplied.")
    if prov != "VALIDATED_OUT_OF_SAMPLE":
        return False, (f"A probability column exists but its provenance is {prov}. In-sample or unverified "
                       "probabilities are refused for weighting.")
    return True, "Validated out-of-sample probabilities supplied."


def group_table(df: pd.DataFrame, group: pd.Series, order: list[str] | None = None) -> list[dict]:
    names = order if order is not None else sorted(group.dropna().unique())
    names = [n for n in names if (group == n).any()]
    rows = []
    for g in names:
        part = df[group == g]
        act = part[active_mask(part)]
        fl = part[part["rule_flagged"]]
        rows.append({
            "group": str(g), "customers": int(len(part)), "active_customers": int(len(act)),
            "flagged_customers": int(len(fl)),
            "flagged_share_of_active": None if act.empty else float(len(fl) / len(act)),
            "flagged_monthly_exposure": sum_or_none(fl["monthly"]) if len(fl) else 0.0,
            "flagged_billing_exposure": sum_or_none(fl["billing"]) if len(fl) else 0.0,
            "expected_monthly_exposure": sum_or_none(act["expected_exposure"]),
            "churned_monthly_context": sum_or_none(part[part["churned"] == True]["monthly"]),   # noqa: E712
        })
    return rows
