"""Explainable, rule-based upsell / cross-sell opportunities. ADVISORY ONLY.

These are observations about service gaps and contract terms - NOT purchase propensities. There are no prices,
conversion probabilities or uplift figures anywhere in this module, and nothing is ever sent to a customer.
Every recommendation has ``requires_human_review = True`` and status ADVISORY_PENDING_HUMAN_REVIEW.
"""
from __future__ import annotations

from typing import Any

import pandas as pd

from ..analytics.config import OpportunityConfig

STATUS = "ADVISORY_PENDING_HUMAN_REVIEW"
INTERNET = ("DSL", "Fiber optic")
# Values meaning "customer has no such service / is not eligible"
NO_SERVICE = {"No internet service", "No phone service"}
TYPE_ADDON = "SERVICE_ADDON_CROSS_SELL"
TYPE_STREAM = "STREAMING_CROSS_SELL"
TYPE_BUNDLE = "PROTECTION_BUNDLE_REVIEW"
TYPE_CONTRACT = "CONTRACT_TERM_REVIEW"
TYPES = (TYPE_ADDON, TYPE_STREAM, TYPE_BUNDLE, TYPE_CONTRACT)
ELIGIBLE, INELIGIBLE_CHURNED, INELIGIBLE_NO_INTERNET, INELIGIBLE_DATA = (
    "ELIGIBLE", "INELIGIBLE_ALREADY_CHURNED", "INELIGIBLE_NO_INTERNET_SERVICE", "INELIGIBLE_INSUFFICIENT_DATA")


def _confidence(missing: list[str]) -> str:
    """Evidence completeness ONLY (not a probability): COMPLETE when every evidence field is present and valid."""
    return "COMPLETE" if not missing else ("PARTIAL" if len(missing) == 1 else "LOW")


def _rec(row: pd.Series, rtype: str, target: str, reason: str, fields: dict[str, Any], missing: list[str],
         eligibility: str, caution: str | None) -> dict[str, Any]:
    return {"customer_id": row["customerID"], "recommendation_type": rtype, "suggested_category": target,
            "reason": reason, "evidence_fields": fields, "eligibility": eligibility,
            "data_confidence": _confidence(missing), "missing_evidence": missing,
            "value_segment": row.get("value_segment"), "status": STATUS, "requires_human_review": True,
            "caution": caution, "quantified_uplift": None}


def customer_recommendations(row: pd.Series, cfg: OpportunityConfig, min_tenure: int | None = None) -> list[dict]:
    recs: list[dict] = []
    churned = row.get("churned")
    caution = ("Customer matches retention screening indicators: review retention needs before any commercial "
               "outreach.") if bool(row.get("rule_flagged", False)) else None
    internet = str(row.get("InternetService", "")) if "InternetService" in row.index else ""
    has_internet_field = "InternetService" in row.index and internet not in ("", "nan")
    if churned == True:    # noqa: E712 - NaN/None (unknown) must not match
        return [_rec(row, TYPE_ADDON, "none", "Customer is labelled as already churned; no offer is suggested.",
                     {"Churn": "Yes"}, [], INELIGIBLE_CHURNED, None)]
    min_ten = cfg.contract_min_tenure if min_tenure is None else min_tenure
    # --- internet service gaps ---
    if not has_internet_field:
        pass
    elif internet in INTERNET:
        have = {s: str(row.get(s, "")) for s in (*cfg.protective, *cfg.streaming) if s in row.index}
        for svc in cfg.protective:
            val = have.get(svc)
            if val is None or val in ("", "nan"):
                continue
            if val == "No":
                recs.append(_rec(row, TYPE_ADDON, svc,
                                 f"Customer has {internet} internet but no {svc}; this is a service gap.",
                                 {"InternetService": internet, svc: val}, [], ELIGIBLE, caution))
        absent_stream = [s for s in cfg.streaming if have.get(s) == "No"]
        if absent_stream and len(absent_stream) == len([s for s in cfg.streaming if s in have]):
            recs.append(_rec(row, TYPE_STREAM, "Streaming services",
                             "Customer has internet service and neither streaming service.",
                             {"InternetService": internet, **{s: "No" for s in absent_stream}}, [], ELIGIBLE, caution))
        prot = [s for s in cfg.protective if s in have and have[s] in ("Yes", "No")]
        count_yes = sum(have[s] == "Yes" for s in prot)
        missing = [s for s in cfg.protective if s not in have or have[s] not in ("Yes", "No")]
        if prot and count_yes <= cfg.bundle_max_protective:
            recs.append(_rec(row, TYPE_BUNDLE, "Protection bundle",
                             f"Customer uses {count_yes} of {len(cfg.protective)} protective services.",
                             {"InternetService": internet, "protective_services_active": count_yes}, missing,
                             ELIGIBLE, caution))
        unknown = [s for s in cfg.protective if s in row.index and str(row.get(s, "")) in ("", "nan")]
        if unknown:
            recs.append(_rec(row, TYPE_ADDON, "service review", "Service fields are missing, so service gaps "
                             "cannot be assessed.", {"InternetService": internet}, unknown, INELIGIBLE_DATA, None))
    elif internet == "No":
        recs.append(_rec(row, TYPE_ADDON, "internet add-ons", "Customer has no internet service; internet add-ons "
                         "do not apply.", {"InternetService": "No"}, [], INELIGIBLE_NO_INTERNET, None))
    # --- contract review ---
    contract, tenure = row.get("Contract"), row.get("tenure_n")
    if isinstance(contract, str) and contract == "Month-to-month" and pd.notna(tenure) and tenure >= min_ten:
        recs.append(_rec(row, TYPE_CONTRACT, "One year or Two year contract",
                         f"Month-to-month customer with {int(tenure)} months of tenure; a longer-term contract "
                         "could be discussed.", {"Contract": contract, "tenure": int(tenure)}, [], ELIGIBLE, caution))
    return recs


def build_recommendations(df: pd.DataFrame, cfg: OpportunityConfig) -> list[dict]:
    out: list[dict] = []
    for _, row in df.iterrows():
        out.extend(customer_recommendations(row, cfg))
    return out
