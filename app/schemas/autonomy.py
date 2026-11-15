"""Phase 11 request/response schemas."""
from __future__ import annotations

from typing import Annotated, Any, Literal

from pydantic import BaseModel, ConfigDict, Field

IdStr = Annotated[str, Field(min_length=1, max_length=64, pattern=r"^[A-Za-z0-9_.\-]+$")]
Status = Literal["pending", "approved", "rejected", "executed", "failed", "cancelled"]
Outcome = Literal["retained", "churned", "no_response"]
Action = Literal["approve", "reject", "cancel", "execute", "fail"]


class _Request(BaseModel):
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)


class PageMeta(BaseModel):
    total: int
    page: int
    page_size: int
    page_count: int


class RecommendationOut(BaseModel):
    recommendation_id: str
    customer_id: str
    category: str
    action_id: str | None
    action_name: str | None
    reason: str
    risk_band: str
    churn_probability: float
    priority: str
    source: str
    rule_id: str
    rules_version: str
    confidence: float | None
    evidence: dict[str, Any]
    status: Status
    created_at: str
    updated_at: str


class RecommendationPage(PageMeta):
    items: list[RecommendationOut]


class RiskEventOut(BaseModel):
    event_id: str
    customer_id: str
    event_type: str
    from_band: str | None
    to_band: str
    probability_before: float | None
    probability_after: float
    detected_at: str
    snapshot_id: int
    source: str
    status: Literal["new", "resolved"]


class RiskEventPage(PageMeta):
    items: list[RiskEventOut]
    monitoring_mode: str = "batch_snapshot_comparison"


class ScanResponse(BaseModel):
    status: Literal["baseline", "unchanged", "compared"]
    snapshot_id: int
    previous_snapshot_id: int | None
    customers: int
    events_created: int
    events_resolved: int
    note: str


class AuditEventOut(BaseModel):
    audit_id: int
    event_type: str
    recommendation_id: str | None
    customer_id: str | None
    from_status: str | None
    to_status: str | None
    actor: str
    actor_authenticated: bool
    detail: str
    created_at: str


class AuditPage(PageMeta):
    items: list[AuditEventOut]


class RecommendationDetail(BaseModel):
    recommendation: RecommendationOut
    audit: list[AuditEventOut]


class GenerateRequest(_Request):
    customer_ids: list[IdStr] = Field(default_factory=list, max_length=500)
    limit: int | None = Field(default=None, ge=1, le=500)


class GenerateResponse(BaseModel):
    considered: int
    created: int
    skipped_existing: int
    rules_version: str
    note: str


class TransitionRequest(_Request):
    note: str | None = Field(default=None, max_length=200)


class TransitionResponse(BaseModel):
    recommendation: RecommendationOut
    replayed: bool


class FeedbackRequest(_Request):
    recommendation_id: IdStr
    outcome: Outcome
    outcome_at: str = Field(min_length=10, max_length=10)
    campaign_id: IdStr | None = None
    data_source: str = Field(min_length=1, max_length=60)


class FeedbackOut(BaseModel):
    feedback_id: str
    recommendation_id: str
    customer_id: str
    recommended_action: str | None
    approval_decision: str
    campaign_id: str | None
    outcome: Outcome
    outcome_at: str
    data_source: str
    observed: bool
    recorded_by: str
    recorded_at: str


class FeedbackPage(PageMeta):
    items: list[FeedbackOut]


class FeedbackResponse(BaseModel):
    feedback: FeedbackOut
    replayed: bool


class LearningResponse(BaseModel):
    validated_outcomes: int
    by_action: list[dict[str, Any]]
    observed_vs_estimated: str
    checks: list[dict[str, Any]]
    learning_enabled: bool
    status: str
    note: str


class StatusOut(BaseModel):
    agent_enabled: bool
    monitoring_enabled: bool
    monitoring_mode: str
    approvals_enabled_in_config: bool
    identity_provider_configured: bool
    approvals_available: bool
    execution_integration: str
    learning_enabled: bool
    rules_version: str


class SummaryResponse(BaseModel):
    status: StatusOut
    recommendations: dict[str, dict[str, int]]
    open_risk_events: dict[str, int]
    latest_snapshot: dict[str, Any] | None
    estimated: dict[str, Any]
    observed: dict[str, int]
    store: dict[str, int]
