"""Per-customer campaign recommendation. Reuses the Phase 4 decision/action evaluation; adds segment peer context
and (optionally) the model's top SHAP drivers. No new financial assumption and no causal claim."""
from __future__ import annotations

from collections import Counter
from collections.abc import Sequence
from dataclasses import dataclass

from retention import ESTIMATE_NOTE
from retention.models import INTERVENE, NO_ACTION_ID, ActionOption, Portfolio, ScoredCustomer
from retention.prioritization import PriorityEntry

BASIS = "phase4_expected_net_benefit_heuristic"
EXPLAINABILITY_NOTE = ("SHAP values describe which features moved the MODEL's churn score; they do not show that "
                       "changing a feature would change the customer's behaviour.")


@dataclass(frozen=True)
class Driver:
    feature: str
    raw_value: object
    shap_value: float
    direction: str


@dataclass(frozen=True)
class Recommendation:
    customer_id: str
    decision: str
    primary_action: ActionOption | None          # None when Phase 4 says do not intervene
    alternatives: tuple[ActionOption, ...]        # other eligible, non-"no action" options, best ENB first
    reasons: tuple[str, ...]
    segment_peer_note: str
    drivers: tuple[Driver, ...]
    explainability_available: bool
    priority_rank: int
    priority_score: float
    priority_tier: str
    basis: str = BASIS
    causal_claim: bool = False
    uplift_available: bool = False
    note: str = ESTIMATE_NOTE
    explainability_note: str = EXPLAINABILITY_NOTE


def _peer_note(customer: ScoredCustomer, portfolio: Portfolio) -> str:
    peers = [c for c in portfolio.customers if c.segment_id == customer.segment_id and c.decision == INTERVENE]
    if not peers:
        return f"No Phase 4 intervention candidates in the '{customer.segment_name}' segment."
    counts = Counter(c.recommended_action for c in peers)
    name, n = counts.most_common(1)[0]
    return (f"{n} of {len(peers)} intervention candidates in '{customer.segment_name}' "
            f"({n / len(peers):.0%}) receive '{name}' from the Phase 4 engine.")


def recommend(customer: ScoredCustomer, portfolio: Portfolio, entry: PriorityEntry,
              drivers: Sequence[Driver] | None = None) -> Recommendation:
    options = sorted((o for o in customer.options if o.action_id != NO_ACTION_ID and o.eligible),
                     key=lambda o: (-o.expected_net_benefit, o.cost, o.action_id))
    primary = next((o for o in options if o.action_id == customer.recommended_action_id), None) \
        if customer.decision == INTERVENE else None
    alternatives = tuple(o for o in options if primary is None or o.action_id != primary.action_id)
    reasons = list(customer.decision_reasons)
    if primary is not None and alternatives:
        reasons.append(f"{len(alternatives)} other eligible action(s) are shown for comparison; "
                       f"none has a higher estimated net benefit.")
    ineligible = [o for o in customer.options if o.action_id != NO_ACTION_ID and not o.eligible]
    for o in ineligible:
        reasons.append(f"'{o.name}' is not eligible: {o.ineligible_reason}.")
    top = tuple(Driver(d.feature, d.raw_value, d.shap_value, d.direction) for d in (drivers or ()))
    return Recommendation(
        customer_id=customer.customer_id, decision=customer.decision, primary_action=primary,
        alternatives=alternatives, reasons=tuple(reasons), segment_peer_note=_peer_note(customer, portfolio),
        drivers=top, explainability_available=bool(top), priority_rank=entry.rank, priority_score=entry.score,
        priority_tier=entry.tier)
