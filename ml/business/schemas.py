"""Typed, immutable data structures for Phase 4. No logic beyond construction-time invariants and ``to_dict``.

``MODEL_EXPLANATION`` (how the model scored a customer) and ``BUSINESS_DECISION`` (what the company might do about
it under configured assumptions) are kept in separate objects on purpose.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Protocol

INTERVENE = "INTERVENE"
DO_NOT_INTERVENE = "DO_NOT_INTERVENE"
DECISIONS = (INTERVENE, DO_NOT_INTERVENE)
NO_ACTION_ID = "no_action"
MODEL_THRESHOLD = "model_threshold"      # policy.min_churn_probability sentinel: use the locked model's threshold

SIMULATION_LABEL = "SIMULATION / WHAT-IF"
NON_CAUSAL_NOTE = (
    "What-if simulation estimates outcomes under configurable assumptions. It does not establish causal "
    "treatment effects: success rates are business assumptions, not measured effects of an intervention."
)


# ------------------------------------------------------------------------------------------------ configuration
@dataclass(frozen=True)
class CurrencyConfig:
    code: str
    symbol: str


@dataclass(frozen=True)
class ClvConfig:
    method: str
    revenue_field: str
    revenue_multiplier: float
    gross_margin: float
    monthly_discount_rate: float
    lifetime_segment_field: str
    lifetime_months_by_segment: dict[str, float]
    default_lifetime_months: float
    allow_default_lifetime: bool


@dataclass(frozen=True)
class RetentionAction:
    action_id: str
    name: str
    cost: float
    success_rate: float
    description: str
    enabled: bool = True
    min_clv: float | None = None

    def to_dict(self) -> dict[str, Any]:
        return {"action_id": self.action_id, "name": self.name, "cost": self.cost,
                "success_rate": self.success_rate, "description": self.description,
                "enabled": self.enabled, "min_clv": self.min_clv}


@dataclass(frozen=True)
class InterventionPolicy:
    min_churn_probability: float | str      # number in [0, 1] or MODEL_THRESHOLD
    min_customer_value: float
    min_expected_net_benefit: float
    max_action_cost: float | None = None


@dataclass(frozen=True)
class RiskBand:
    name: str
    min_probability: float


@dataclass(frozen=True)
class WhatIfDefaults:
    probability_sweep: tuple[float, float, float]      # start, stop, step
    success_rate_multipliers: tuple[float, ...]
    cost_multipliers: tuple[float, ...]


@dataclass(frozen=True)
class BusinessConfig:
    currency: CurrencyConfig
    clv: ClvConfig
    actions: dict[str, RetentionAction]
    policy: InterventionPolicy
    risk_bands: tuple[RiskBand, ...]
    what_if: WhatIfDefaults


# ----------------------------------------------------------------------------------------------- calculations
@dataclass(frozen=True)
class ClvResult:
    clv: float
    monthly_revenue: float
    lifetime_months: float
    lifetime_source: str            # "segment:<value>" or "default"
    gross_margin: float
    monthly_discount_rate: float
    discounted_months: float        # months after discounting; equals lifetime_months when the rate is 0

    def to_dict(self) -> dict[str, Any]:
        return dict(self.__dict__)


@dataclass(frozen=True)
class EnbBreakdown:
    """Every component of ENB, so the calculation can be audited line by line."""
    clv: float
    churn_probability: float
    value_at_risk: float                 # clv * churn_probability
    action_success_rate: float
    action_cost: float
    expected_benefit: float              # value_at_risk * action_success_rate
    expected_cost: float                 # the action cost (paid with certainty when the action is taken)
    expected_net_benefit: float          # expected_benefit - expected_cost

    def to_dict(self) -> dict[str, float]:
        return dict(self.__dict__)


@dataclass(frozen=True)
class ActionEvaluation:
    action: RetentionAction
    eligible: bool
    ineligible_reason: str | None
    enb: EnbBreakdown

    def to_dict(self) -> dict[str, Any]:
        return {**self.action.to_dict(), "eligible": self.eligible, "ineligible_reason": self.ineligible_reason,
                **self.enb.to_dict()}


@dataclass(frozen=True)
class DecisionReason:
    code: str
    values: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return {"code": self.code, "values": dict(self.values)}


@dataclass(frozen=True)
class ResolvedPolicy:
    """The policy with ``model_threshold`` replaced by the concrete number used for this decision."""
    min_churn_probability: float
    min_customer_value: float
    min_expected_net_benefit: float
    max_action_cost: float | None


@dataclass(frozen=True)
class DecisionResult:
    decision: str
    recommended: ActionEvaluation              # no_action unless the decision is INTERVENE
    best_eligible: ActionEvaluation | None     # best action by ENB if the customer-level gates were ignored
    reasons: tuple[DecisionReason, ...]
    policy: ResolvedPolicy
    evaluations: tuple[ActionEvaluation, ...]  # every enabled action, in a fixed order, for audit


@dataclass(frozen=True)
class CustomerBusinessProfile:
    """Business-level view of one customer. Numbers come from the model probability, the record and the config."""
    customer_id: str | None
    churn_probability: float
    risk_band: str
    clv: float
    value_at_risk: float
    recommended_action: str
    recommended_action_id: str
    action_cost: float
    action_success_rate: float
    expected_benefit: float
    expected_cost: float
    expected_net_benefit: float
    intervention_decision: str
    decision_reasons: tuple[DecisionReason, ...]
    decision_reason_messages: tuple[str, ...]
    currency: str
    clv_detail: ClvResult
    action_evaluations: tuple[ActionEvaluation, ...]
    policy: ResolvedPolicy
    notice: str = NON_CAUSAL_NOTE

    def to_dict(self) -> dict[str, Any]:
        return {
            "customer_id": self.customer_id, "churn_probability": self.churn_probability,
            "risk_band": self.risk_band, "clv": self.clv, "value_at_risk": self.value_at_risk,
            "recommended_action": self.recommended_action, "recommended_action_id": self.recommended_action_id,
            "action_cost": self.action_cost, "action_success_rate": self.action_success_rate,
            "expected_benefit": self.expected_benefit, "expected_cost": self.expected_cost,
            "expected_net_benefit": self.expected_net_benefit,
            "intervention_decision": self.intervention_decision,
            "decision_reasons": [r.to_dict() for r in self.decision_reasons],
            "decision_reason_messages": list(self.decision_reason_messages),
            "currency": self.currency, "clv_detail": self.clv_detail.to_dict(),
            "policy": dict(self.policy.__dict__),
            "action_evaluations": [e.to_dict() for e in self.action_evaluations],
            "notice": self.notice,
        }


# ------------------------------------------------------------------------------------------------ explanation
class ContributionLike(Protocol):
    """Structural match for ``ml.explainability.schemas.FeatureContribution`` (no import of shap needed)."""
    source_feature: str
    shap_value: float
    direction: str


class ExplanationLike(Protocol):
    """Structural match for ``ml.explainability.schemas.LocalExplanation``."""
    features: list[Any]


@dataclass(frozen=True)
class BusinessExplanation:
    """Two clearly separated sections: what the MODEL did, and what the BUSINESS DECISION is under assumptions."""
    model_explanation: str
    business_decision: str
    disclaimer: str

    def to_dict(self) -> dict[str, str]:
        return {"MODEL EXPLANATION": self.model_explanation, "BUSINESS DECISION": self.business_decision,
                "disclaimer": self.disclaimer}
