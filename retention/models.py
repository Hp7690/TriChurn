"""Immutable result types shared by the retention modules (no framework imports)."""
from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass, field

INTERVENE = "INTERVENE"
DO_NOT_INTERVENE = "DO_NOT_INTERVENE"
NO_ACTION_ID = "no_action"


@dataclass(frozen=True)
class ActionOption:
    """One Phase 4 action evaluated for one customer (all figures are ESTIMATES under assumed success rates)."""
    action_id: str
    name: str
    cost: float
    success_rate: float
    eligible: bool
    ineligible_reason: str | None
    expected_benefit: float
    expected_net_benefit: float


@dataclass(frozen=True)
class ScoredCustomer:
    customer_id: str
    churn_probability: float
    risk_band: str
    segment_id: int
    segment_name: str
    clv: float
    value_at_risk: float
    decision: str
    recommended_action_id: str
    recommended_action: str
    action_cost: float
    action_success_rate: float
    expected_benefit: float
    expected_net_benefit: float
    decision_reasons: tuple[str, ...]
    options: tuple[ActionOption, ...]
    features: Mapping[str, object] = field(default_factory=dict)


@dataclass(frozen=True)
class Portfolio:
    """Every customer scored once by the locked pipeline. Immutable; rescoring requires a restart."""
    customers: tuple[ScoredCustomer, ...]
    currency_code: str
    currency_symbol: str
    model_version: str
    model_sha256: str
    segmentation_version: str
    segmentation_sha256: str
    dataset_sha256: str
    decision_threshold: float
    scored_at: str
    action_catalogue: tuple[ActionOption, ...]            # per-customer fields are placeholders: cost/rate/name only
    dataset_columns: tuple[str, ...] = ()
    index: Mapping[str, ScoredCustomer] = field(default_factory=dict)

    def get(self, customer_id: str) -> ScoredCustomer | None:
        return self.index.get(customer_id)
