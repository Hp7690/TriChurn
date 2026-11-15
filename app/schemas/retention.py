"""Phase 9 request/response schemas. Requests forbid unknown fields; responses carry explicit ESTIMATE/OBSERVATION
labels so a client cannot mistake an assumption-based figure for a measured result."""
from __future__ import annotations

from typing import Annotated, Literal

from pydantic import BaseModel, ConfigDict, Field

IdStr = Annotated[str, Field(min_length=1, max_length=64, pattern=r"^[A-Za-z0-9_.\-]+$")]
Decision = Literal["INTERVENE", "DO_NOT_INTERVENE"]
Group = Literal["treatment", "control", "unspecified"]
Outcome = Literal["retained", "churned", "no_response"]


class _Request(BaseModel):
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)


# ------------------------------------------------------------------------------------------------ shared
class ActionOptionOut(BaseModel):
    action_id: str
    name: str
    cost: float
    success_rate: float
    eligible: bool
    ineligible_reason: str | None = None
    expected_benefit: float
    expected_net_benefit: float


class CustomerSnapshot(BaseModel):
    customer_id: str
    churn_probability: float
    risk_band: str
    segment_id: int
    segment_name: str
    clv: float
    value_at_risk: float
    decision: Decision
    recommended_action_id: str
    recommended_action: str
    action_cost: float
    action_success_rate: float
    expected_net_benefit: float


# ------------------------------------------------------------------------------------------------ summary
class RiskBandSummaryOut(BaseModel):
    risk_band: str
    customers: int
    value_at_risk: float
    total_clv: float


class SegmentSummaryOut(BaseModel):
    segment_id: int
    segment_name: str
    customers: int
    value_at_risk: float
    intervention_candidates: int
    average_churn_probability: float


class CampaignEstimateOut(BaseModel):
    action_id: str
    action_name: str
    customers: int
    cost_per_customer: float
    assumed_success_rate: float
    estimated_total_cost: float
    estimated_retained_revenue: float
    estimated_net_benefit: float
    estimated_roi: float | None


class PriorityItem(BaseModel):
    rank: int
    score: float
    tier: str
    customer: CustomerSnapshot
    value_at_risk_percentile: float
    churn_probability_percentile: float
    expected_net_benefit_percentile: float
    reasons: list[str] = Field(default_factory=list)


class ExecutiveSummaryResponse(BaseModel):
    kind: Literal["estimate"] = "estimate"
    currency_code: str
    currency_symbol: str
    total_customers: int
    average_churn_probability: float
    revenue_at_risk: float
    intervention_candidates: int
    high_priority_customers: int
    high_priority_value_at_risk: float
    by_risk_band: list[RiskBandSummaryOut]
    by_segment: list[SegmentSummaryOut]
    recommended_campaigns: list[CampaignEstimateOut]
    estimated_total_cost: float
    estimated_retained_revenue: float
    estimated_net_benefit: float
    estimated_roi: float | None
    top_priorities: list[PriorityItem]
    model_version: str
    segmentation_version: str
    dataset_sha256: str
    scored_at: str
    note: str
    score_note: str


# ---------------------------------------------------------------------------------------------- priorities
class PriorityPageResponse(BaseModel):
    items: list[PriorityItem]
    total: int
    page: int
    page_size: int
    page_count: int
    score_note: str


# ------------------------------------------------------------------------------------------ recommendation
class DriverOut(BaseModel):
    feature: str
    raw_value: str | int | float | bool | None = None
    shap_value: float
    direction: str


class RecommendationResponse(BaseModel):
    customer_id: str
    decision: Decision
    primary_action: ActionOptionOut | None
    alternatives: list[ActionOptionOut]
    reasons: list[str]
    segment_peer_note: str
    drivers: list[DriverOut]
    explainability_available: bool
    priority_rank: int
    priority_score: float
    priority_tier: str
    basis: str
    causal_claim: bool
    uplift_available: bool
    note: str
    explainability_note: str


# --------------------------------------------------------------------------------------------- simulator
class ScenarioRequest(_Request):
    name: str | None = Field(default=None, max_length=80)
    action_id: IdStr
    cost_override: float | None = Field(default=None, ge=0, le=1e9)
    success_rate_override: float | None = Field(default=None, ge=0, le=1)
    decision_filter: Literal["intervene", "any"] = "intervene"
    risk_bands: list[str] = Field(default_factory=list, max_length=10)
    segment_ids: list[int] = Field(default_factory=list, max_length=20)
    min_churn_probability: float | None = Field(default=None, ge=0, le=1)
    top_n: int | None = Field(default=None, ge=1, le=10000)
    customer_ids: list[IdStr] = Field(default_factory=list, max_length=10000)


class SimulateRequest(_Request):
    scenarios: list[ScenarioRequest] = Field(min_length=1, max_length=10)


class ScenarioResultOut(BaseModel):
    name: str
    action_id: str
    action_name: str
    cost_per_customer: float
    cost_source: str
    success_rate: float
    success_rate_source: str
    targeted_customers: int
    eligible_customers: int
    excluded_ineligible: int
    total_value_at_risk: float
    total_cost: float
    estimated_retained_revenue: float
    estimated_net_benefit: float
    estimated_roi: float | None
    expected_retained_customers: float
    cost_per_expected_retained_customer: float | None
    label: Literal["ESTIMATE"]
    note: str


class SimulateResponse(BaseModel):
    results: list[ScenarioResultOut]
    best_by_net_benefit_index: int | None
    best_by_roi_index: int | None
    label: Literal["ESTIMATE"]
    note: str


class ActionsResponse(BaseModel):
    currency_code: str
    currency_symbol: str
    actions: list[ActionOptionOut]
    source: str = "configs/business.yaml (Phase 4); success rates are assumptions, not measured effects"


# ----------------------------------------------------------------------------------------------- campaigns
class CampaignCreateRequest(_Request):
    name: str = Field(min_length=1, max_length=120)
    action_id: IdStr
    campaign_date: str = Field(min_length=10, max_length=10)          # ISO date, validated by the domain layer
    randomized: bool = False
    notes: str | None = Field(default=None, max_length=500)


class CampaignOut(BaseModel):
    campaign_id: str
    name: str
    action_id: str
    campaign_date: str
    randomized: bool
    notes: str | None
    created_at: str


class CampaignListResponse(BaseModel):
    campaigns: list[CampaignOut]


class AssignRequest(_Request):
    customer_ids: list[IdStr] = Field(min_length=1, max_length=5000)
    group: Group = "unspecified"


class AssignResponse(BaseModel):
    campaign_id: str
    requested: int
    assigned: int
    unknown_customer_ids: list[str]
    ineligible_customer_ids: list[str]
    already_assigned_ids: list[str]


class OutcomeItem(_Request):
    customer_id: IdStr
    outcome: Outcome
    actual_cost: float | None = Field(default=None, ge=0, le=1e9)
    actual_retained_revenue: float | None = Field(default=None, ge=0, le=1e12)


class OutcomeRequest(_Request):
    outcomes: list[OutcomeItem] = Field(min_length=1, max_length=5000)


class OutcomeResponse(BaseModel):
    campaign_id: str
    requested: int
    recorded: int
    not_assigned_ids: list[str]
    already_recorded_ids: list[str]


class CampaignMetricsOut(BaseModel):
    campaign_id: str
    name: str
    action_id: str
    campaign_date: str
    randomized: bool
    assigned: int
    outcomes_recorded: int
    outcome_coverage: float | None
    retained: int
    churned: int
    no_response: int
    observed_retention_rate: float | None
    estimated_cost: float
    estimated_benefit: float
    actual_cost: float | None
    actual_retained_revenue: float | None
    actual_net_benefit: float | None
    actual_roi: float | None
    note: str


class AnalyticsResponse(BaseModel):
    campaigns: list[CampaignMetricsOut]
    total_assigned: int
    total_outcomes_recorded: int
    total_estimated_cost: float
    total_estimated_benefit: float
    total_actual_cost: float | None
    total_actual_retained_revenue: float | None
    note: str


class ReadinessCheckOut(BaseModel):
    code: str
    passed: bool
    detail: str


class UpliftReadinessResponse(BaseModel):
    ready: bool
    status: str
    dataset_treatment_columns: list[str]
    treatment_assignments: int
    control_assignments: int
    unspecified_assignments: int
    outcomes_recorded: int
    checks: list[ReadinessCheckOut]
    requirements: list[str]
    note: str
