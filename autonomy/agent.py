"""Deterministic retention agent (rules-1.0.0). No LLM, no tools, no external calls: it only turns already-computed
Phase 2/4/5/9 results and a few account features into explained recommendations.

Rules
  R1  Phase 4 says INTERVENE            -> category from the Phase 4 action (config map); cites cost, assumed success
                                           rate and the ESTIMATED net benefit.
  R2  risk in configured bands AND internet service without a tech-support add-on
                                        -> customer_support_followup
  R3  risk in configured bands AND month-to-month contract AND tenure <= configured months
                                        -> subscription_review
  (service_issue_investigation is NOT implemented: it needs ticket/outage data that does not exist.)

Rules R2/R3 are observations about account data, not claims that those attributes cause churn. ``confidence`` is
always None: no calibrated evidence supports a confidence value, and churn probability is not response probability.
"""
from __future__ import annotations

import hashlib
from collections.abc import Callable, Iterable
from dataclasses import dataclass
from typing import Any

from autonomy import ESTIMATE_NOTE
from autonomy.config import AutonomyConfig
from autonomy.models import PENDING, PRIORITIES, Recommendation
from autonomy.store import new_id
from retention.models import INTERVENE, NO_ACTION_ID, Portfolio, ScoredCustomer
from retention.prioritization import PriorityEntry

SOURCE = "phase9_portfolio"


@dataclass(frozen=True)
class Draft:
    recommendation: Recommendation
    fingerprint: str


def fingerprint(customer_id: str, category: str, action_id: str | None, rules_version: str) -> str:
    raw = "|".join((customer_id, category, action_id or "-", rules_version))
    return hashlib.sha256(raw.encode()).hexdigest()


def _priority(entry: PriorityEntry) -> str:
    return entry.tier if entry.tier in PRIORITIES else "P4"


def _base_evidence(c: ScoredCustomer, entry: PriorityEntry, currency: str) -> dict[str, Any]:
    return {
        "source": SOURCE,
        "risk": {"churn_probability": c.churn_probability, "risk_band": c.risk_band, "is_estimate": False,
                 "note": "Output of the locked Phase 2 churn model; this is churn risk, not response likelihood."},
        "priority": {"tier": entry.tier, "score": entry.score, "rank": entry.rank,
                     "note": "Heuristic ranking score (not a probability)."},
        "segment": c.segment_name,
        "currency": currency,
    }


def evaluate(entry: PriorityEntry, portfolio: Portfolio, config: AutonomyConfig,
             now: Callable[[], str]) -> list[Draft]:
    c = entry.customer
    drafts: list[Draft] = []
    stamp = now()

    def add(category: str, rule_id: str, action_id: str | None, action_name: str | None, reason: str,
            evidence: dict[str, Any]) -> None:
        rec = Recommendation(
            recommendation_id=new_id("rec"), customer_id=c.customer_id, category=category, action_id=action_id,
            action_name=action_name, reason=reason, risk_band=c.risk_band, churn_probability=c.churn_probability,
            priority=_priority(entry), source=SOURCE, rule_id=rule_id, rules_version=config.rules_version,
            confidence=None, evidence={**evidence, "rule_id": rule_id, "rules_version": config.rules_version},
            status=PENDING, created_at=stamp, updated_at=stamp)
        drafts.append(Draft(rec, fingerprint(c.customer_id, category, action_id, config.rules_version)))

    base = _base_evidence(c, entry, portfolio.currency_code)
    category = config.action_categories.get(c.recommended_action_id)
    if c.decision == INTERVENE and c.recommended_action_id != NO_ACTION_ID and category is not None:
        add(category, "R1", c.recommended_action_id, c.recommended_action,
            f"Phase 4 decision is to intervene with '{c.recommended_action}' (estimated net benefit "
            f"{portfolio.currency_symbol}{c.expected_net_benefit:,.0f} under an ASSUMED {c.action_success_rate:.0%} "
            f"success rate). " + " ".join(c.decision_reasons[:1]),
            {**base, "phase4": {"decision": c.decision, "action_id": c.recommended_action_id,
                                "action_cost": c.action_cost, "assumed_success_rate": c.action_success_rate,
                                "estimated_net_benefit": c.expected_net_benefit, "is_estimate": True,
                                "note": ESTIMATE_NOTE}})

    features = c.features
    high = c.risk_band in config.evidence_risk_bands
    if high and features.get("InternetService") not in (None, "No") and features.get("TechSupport") == "No":
        add("customer_support_followup", "R2", None, None,
            f"{c.risk_band} churn risk and the account has internet service but no tech-support add-on (rule R2). "
            "This is an observation from account data, not evidence that the missing add-on causes churn.",
            {**base, "features": {"InternetService": features.get("InternetService"), "TechSupport": "No"}})
    tenure = features.get("tenure")
    if high and features.get("Contract") == "Month-to-month" and isinstance(tenure, int | float) \
            and tenure <= config.subscription_review_max_tenure:
        add("subscription_review", "R3", None, None,
            f"{c.risk_band} churn risk on a month-to-month contract with tenure of {int(tenure)} months or less "
            "(rule R3). A review of plan fit may help; this is a rule, not a prediction of the customer's response.",
            {**base, "features": {"Contract": "Month-to-month", "tenure_months": tenure}})
    return drafts


def generate(entries: Iterable[PriorityEntry], portfolio: Portfolio, config: AutonomyConfig,
             now: Callable[[], str]) -> list[Draft]:
    out: list[Draft] = []
    for entry in entries:
        out.extend(evaluate(entry, portfolio, config, now))
    return out
