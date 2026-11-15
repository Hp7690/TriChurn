"""Phase 4 business decision response. All money figures are estimates under configured assumptions."""
from __future__ import annotations

from typing import Any, Literal

from pydantic import BaseModel


class DecisionReasonOut(BaseModel):
    code: str
    values: dict[str, Any]


class ActionEvaluationOut(BaseModel):
    action_id: str
    name: str
    cost: float
    success_rate: float
    eligible: bool
    ineligible_reason: str | None
    expected_benefit: float
    expected_cost: float
    expected_net_benefit: float


class BusinessExplanationOut(BaseModel):
    model_explanation: str
    business_decision: str
    disclaimer: str


class BusinessResponse(BaseModel):
    customer_id: str | None
    churn_probability: float
    risk_band: str
    currency: str
    clv: float
    value_at_risk: float
    intervention_decision: Literal["INTERVENE", "DO_NOT_INTERVENE"]
    recommended_action_id: str
    recommended_action: str
    action_cost: float
    action_success_rate: float
    expected_benefit: float
    expected_cost: float
    expected_net_benefit: float
    decision_reasons: list[DecisionReasonOut]
    decision_reason_messages: list[str]
    action_evaluations: list[ActionEvaluationOut]
    explanation: BusinessExplanationOut
    notice: str
