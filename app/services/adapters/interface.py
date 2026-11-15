"""Adapter port (``Phase15Port``) and framework-free result DTOs.

Any object that implements ``Phase15Port`` can be injected into ``create_app(adapter=...)`` or returned by a custom
``TRICHURN_ADAPTER_FACTORY``; routes and services never change. DTOs carry no pydantic/FastAPI/ml types, and the
explanation DTO is shaped like the Phase 3 ``LocalExplanation`` (``features[i].source_feature/.direction/.raw_value``)
so it can be handed straight back to the Phase 4 business explainer.
"""
from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass, field
from typing import Any, Protocol, runtime_checkable

# capability names used in readiness checks and 503 errors
CAP_MODEL = "phase2_model"
CAP_BUSINESS = "business_engine"
CAP_EXPLAIN = "explainability"
CAP_SEGMENT = "segmentation"
CAP_SCHEMA = "feature_schema"
CAP_MODULES = "phase1_5_modules"


@dataclass(frozen=True)
class PredictionResult:
    churn_probability: float
    predicted_churn: bool
    decision_threshold: float
    risk_band: str
    model_name: str
    model_version: str


@dataclass(frozen=True)
class FeatureContribution:
    source_feature: str
    raw_value: Any
    shap_value: float
    direction: str
    is_engineered: bool = False


@dataclass(frozen=True)
class ExplanationResult:
    prediction_probability: float
    predicted_class: int
    threshold: float
    base_value: float
    output_space: str
    model_log_odds: float
    reconstruction_error: float
    features: list[FeatureContribution]          # sorted by |shap_value| descending (Phase 3 order)
    interpretation: str
    model_version: str


@dataclass(frozen=True)
class DecisionReason:
    code: str
    values: Mapping[str, Any]


@dataclass(frozen=True)
class ActionEvaluation:
    action_id: str
    name: str
    cost: float
    success_rate: float
    eligible: bool
    ineligible_reason: str | None
    expected_benefit: float
    expected_cost: float
    expected_net_benefit: float


@dataclass(frozen=True)
class BusinessExplanation:
    model_explanation: str
    business_decision: str
    disclaimer: str


@dataclass(frozen=True)
class BusinessResult:
    churn_probability: float
    risk_band: str
    currency: str
    clv: float
    value_at_risk: float
    intervention_decision: str
    recommended_action_id: str
    recommended_action: str
    action_cost: float
    action_success_rate: float
    expected_benefit: float
    expected_cost: float
    expected_net_benefit: float
    decision_reasons: list[DecisionReason]
    decision_reason_messages: list[str]
    action_evaluations: list[ActionEvaluation]
    explanation: BusinessExplanation
    notice: str


@dataclass(frozen=True)
class SegmentResult:
    segment_id: int
    segment_name: str
    distance_to_centroid: float
    model_version: str
    segment_count: int
    customer_count: int | None
    priority_rank: int | None
    priority_tier: str | None
    note: str


@dataclass(frozen=True)
class CheckResult:
    name: str
    ok: bool
    detail: str          # short, sanitised code-like text: never a path, exception text or environment value


@dataclass(frozen=True)
class ReadinessReport:
    checks: tuple[CheckResult, ...]
    details: Mapping[str, Any] = field(default_factory=dict)

    @property
    def ready(self) -> bool:
        return bool(self.checks) and all(c.ok for c in self.checks)


@runtime_checkable
class Phase15Port(Protocol):
    """What the API layer needs from the locked Phase 1-5 implementation.

    ``customer`` is the validated feature mapping (exactly the 19 raw model features, ``TotalCharges`` may be None
    for tenure 0). Implementations must raise ``app.core.errors.ApiError`` for client-safe failures and must never
    retrain, refit (no ``KMeans.fit``), recalibrate or write artifacts.
    """

    is_test_double: bool

    def warm_up(self) -> None: ...

    def readiness(self) -> ReadinessReport: ...

    def predict(self, customer: Mapping[str, Any]) -> PredictionResult: ...

    def explain(self, customer: Mapping[str, Any]) -> ExplanationResult: ...

    def business(self, customer: Mapping[str, Any], churn_probability: float | None = None,
                 explanation: ExplanationResult | None = None) -> BusinessResult: ...

    def segment(self, customer: Mapping[str, Any]) -> SegmentResult: ...
