"""Phase 12 HTTP schemas (typed responses; strict request validation)."""
from __future__ import annotations

from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field

Status = Literal["ACTUAL", "ESTIMATED", "PROXY", "ILLUSTRATIVE", "UNAVAILABLE", "BLOCKED_BY_MISSING_DATA"]
Scalar = float | int | str | None


class _Out(BaseModel):
    model_config = ConfigDict(extra="ignore")


class Meta(_Out):
    calculated_at: str
    data_source: str
    methodology_note: str
    package_version: str


class Page(Meta):
    total: int
    page: int
    page_size: int
    page_count: int


class Metric(_Out):
    key: str
    name: str
    description: str
    value: Scalar = None
    unit: str
    status: Status
    formula: str
    source_fields: list[str]
    assumptions: list[str]
    limitations: list[str]
    reason: str | None = None
    calculated_at: str


class Quality(_Out):
    rows_read: int
    rows_used: int
    duplicate_ids_dropped: int
    missing_customer_id: int
    invalid_tenure: int
    invalid_monthly_charges: int
    missing_total_charges: int
    invalid_total_charges: int
    zero_tenure_rows: int
    inconsistent_total_vs_monthly: int
    churn_unknown: int
    missing_columns: list[str]
    notes: list[str]


class SegmentRow(_Out):
    segment: str
    customers: int
    customer_share: float
    observed_billing_total: float | None = None
    observed_billing_share: float | None = None
    avg_observed_billing: float | None = None
    avg_estimated_clv: float | None = None
    monthly_recurring_total: float | None = None
    churned_customers: int
    churn_rate: float | None = None
    churn_known_customers: int


class HistBin(_Out):
    lower: float
    upper: float
    count: int


class Scenario(_Out):
    status: Status
    assumptions_confirmed: bool
    remaining_months_by_contract: dict[str, float]
    monthly_discount_rate: float
    reason: str | None = None


class ClvSummaryResponse(Meta):
    metrics: list[Metric]
    scenario: Scenario
    distribution_observed_billing: list[HistBin]
    distribution_estimated_clv: list[HistBin]
    distribution_status: Status
    distribution_observed_billing_status: Status
    distribution_estimated_clv_status: Status
    customers_without_valid_billing: int
    customers_with_inconsistent_billing: int
    data_quality: Quality


class ClvCustomer(_Out):
    customer_id: str
    contract: str | None = None
    tenure_months: float | None = None
    monthly_charges: float | None = None
    observed_billing: float | None = None
    observed_billing_status: Status
    estimated_forward_value: float | None = None
    estimated_clv: float | None = None
    estimated_clv_status: Status
    value_segment: str
    churned: bool | None = None
    billing_inconsistent: bool


class ClvCustomersResponse(Page):
    items: list[ClvCustomer]


class ClvSegmentsResponse(Meta):
    metric: str
    method: str
    metric_status: Status
    reason: str | None = None
    thresholds: list[float] | None = None
    labels: list[str]
    note: str
    segments: list[SegmentRow]


class RiskGroupRow(_Out):
    group: str
    customers: int
    active_customers: int
    flagged_customers: int
    flagged_share_of_active: float | None = None
    flagged_monthly_exposure: float | None = None
    flagged_billing_exposure: float | None = None
    expected_monthly_exposure: float | None = None
    churned_monthly_context: float | None = None


class ProbabilityWeighting(_Out):
    available: bool
    reason: str
    provenance: str


class RuleDefinition(_Out):
    indicators: dict[str, Any]
    min_indicators_to_flag: int
    status: Status
    is_probability: bool


class RiskSummaryResponse(Meta):
    metrics: list[Metric]
    flagged_customers: int
    active_customers: int
    probability_weighting: ProbabilityWeighting
    rule_definition: RuleDefinition
    by_contract: list[RiskGroupRow]
    by_tenure_group: list[RiskGroupRow]
    by_value_segment: list[RiskGroupRow]
    warnings: list[str]


class RiskCustomer(_Out):
    customer_id: str
    contract: str | None = None
    tenure_months: float | None = None
    tenure_group: str
    value_segment: str
    monthly_charges: float | None = None
    observed_billing: float | None = None
    indicators: list[str]
    indicator_count: int
    exposure_basis: str
    exposure_status: Status
    churn_probability: float | None = None
    expected_monthly_exposure: float | None = None


class RiskCustomersResponse(Page):
    items: list[RiskCustomer]


class OpportunitiesSummaryResponse(Meta):
    metrics: list[Metric]
    customers_with_opportunity: int
    total_recommendations: int
    eligible_recommendations: int
    by_type: dict[str, int]
    by_target: dict[str, int]
    by_value_segment: dict[str, int]
    by_eligibility: dict[str, int]
    by_data_confidence: dict[str, int]
    requires_human_review: bool
    warnings: list[str]


class Opportunity(_Out):
    customer_id: str
    recommendation_type: str
    suggested_category: str
    reason: str
    evidence_fields: dict[str, Any]
    eligibility: str
    data_confidence: str
    missing_evidence: list[str]
    value_segment: str | None = None
    status: str
    requires_human_review: bool
    caution: str | None = None
    quantified_uplift: None = None


class OpportunitiesCustomersResponse(Page):
    items: list[Opportunity]


class CohortRow(_Out):
    cohort: str
    customers: int
    customer_share: float
    churned_customers: int
    churn_rate: float | None = None
    avg_monthly_charges: float | None = None
    avg_observed_billing: float | None = None
    avg_estimated_clv: float | None = None
    monthly_recurring_total: float | None = None
    observed_billing_total: float | None = None


class BlockedAnalysis(_Out):
    analysis: str
    status: Status
    reason: str


class AcquisitionBlock(_Out):
    status: str
    reason: str | None = None
    cohorts: list[dict[str, Any]]


class CohortSummaryResponse(Meta):
    method: str
    status: Status
    metrics: list[Metric]
    supported_now: list[str]
    blocked_by_missing_data: list[BlockedAnalysis]
    acquisition_cohorts: AcquisitionBlock
    tenure_buckets: list[CohortRow]
    limitations: list[str]


class CohortTenureResponse(Meta):
    method: str
    status: Status
    limitations: list[str]
    tenure_buckets: list[CohortRow]
    lifecycle_groups: list[CohortRow]
    contract_cohorts: list[CohortRow]


class ForecastRow(BaseModel):
    model_config = ConfigDict(extra="forbid")
    period: str = Field(max_length=40)
    customer_id: str = Field(min_length=1, max_length=64)
    revenue: float | str | None = None
    product: str | None = Field(default=None, max_length=64)
    segment: str | None = Field(default=None, max_length=64)


class ForecastValidateRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")
    rows: list[ForecastRow] = Field(default_factory=list, max_length=200_000)
    run_backtest: bool = False


class ForecastReadinessResponse(Meta):
    state: str
    readiness: dict[str, Any]
    schema_: dict[str, Any] = Field(alias="schema")
    metrics: list[Metric]
    requirements: dict[str, Any]
    note: str
    backtest: dict[str, Any] | None = None
    model_config = ConfigDict(extra="ignore", populate_by_name=True)


class ModuleAvailability(_Out):
    module: str
    status: Status
    detail: str


class AvailabilityResponse(Meta):
    modules: list[ModuleAvailability]
    data_quality: Quality
    status_legend: dict[str, str]
    metric_definitions: list[dict[str, Any]]
    independence: dict[str, bool]


class SummaryResponse(Meta):
    headline_metrics: list[Metric]
    clv: dict[str, Any]
    risk: dict[str, Any]
    opportunities: dict[str, Any]
    cohorts: list[CohortRow]
    forecast_state: str
    data_quality: Quality
    warnings: list[str]
