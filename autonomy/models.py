from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

PENDING, APPROVED, REJECTED, EXECUTED, FAILED, CANCELLED = (
    "pending", "approved", "rejected", "executed", "failed", "cancelled")
STATUSES = (PENDING, APPROVED, REJECTED, EXECUTED, FAILED, CANCELLED)
TRANSITIONS: dict[str, tuple[str, ...]] = {
    PENDING: (APPROVED, REJECTED, CANCELLED),
    APPROVED: (EXECUTED, FAILED, CANCELLED),
    REJECTED: (), EXECUTED: (), FAILED: (), CANCELLED: (),
}
PRIORITIES = ("P1", "P2", "P3", "P4")
CATEGORIES = ("personalized_offer", "customer_support_followup", "subscription_review",
              "retention_campaign_enrollment")
OUTCOMES = ("retained", "churned", "no_response")


@dataclass(frozen=True)
class Recommendation:
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
    confidence: float | None          # always None today: no calibrated evidence supports a confidence value
    evidence: dict[str, Any]
    status: str
    created_at: str
    updated_at: str


@dataclass(frozen=True)
class RiskEvent:
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
    status: str                       # new | resolved


@dataclass(frozen=True)
class AuditEvent:
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


@dataclass(frozen=True)
class Feedback:
    feedback_id: str
    recommendation_id: str
    customer_id: str
    recommended_action: str | None
    approval_decision: str
    campaign_id: str | None
    outcome: str
    outcome_at: str
    data_source: str
    observed: bool
    recorded_by: str
    recorded_at: str


@dataclass(frozen=True)
class SnapshotRow:
    customer_id: str
    churn_probability: float
    risk_band: str
    decision: str


@dataclass(frozen=True)
class SnapshotInfo:
    snapshot_id: int
    fingerprint: str
    created_at: str
    customer_count: int


@dataclass(frozen=True)
class Page:
    items: tuple[Any, ...]
    total: int
    page: int
    page_size: int
    page_count: int
    extra: dict[str, Any] = field(default_factory=dict)
