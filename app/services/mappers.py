"""Pure DTO -> response-schema mapping. No calculations happen here."""
from __future__ import annotations

from app.schemas.business import (
    ActionEvaluationOut,
    BusinessExplanationOut,
    BusinessResponse,
    DecisionReasonOut,
)
from app.schemas.explainability import ExplainResponse, FeatureContributionOut
from app.schemas.prediction import PredictionResponse
from app.schemas.segmentation import SegmentResponse
from app.services.adapters.interface import BusinessResult, ExplanationResult, PredictionResult, SegmentResult


def to_prediction(customer_id: str | None, r: PredictionResult) -> PredictionResponse:
    return PredictionResponse(
        customer_id=customer_id, churn_probability=r.churn_probability, predicted_churn=r.predicted_churn,
        predicted_label="CHURN" if r.predicted_churn else "NO_CHURN", decision_threshold=r.decision_threshold,
        risk_band=r.risk_band, model_name=r.model_name, model_version=r.model_version)


def to_explanation(customer_id: str | None, r: ExplanationResult, top_n: int | None = None) -> ExplainResponse:
    features = r.features if top_n is None else r.features[:top_n]       # already sorted by |SHAP| (Phase 3)
    return ExplainResponse(
        customer_id=customer_id, churn_probability=r.prediction_probability, predicted_churn=r.predicted_class == 1,
        decision_threshold=r.threshold, output_space=r.output_space, base_value=r.base_value,
        model_log_odds=r.model_log_odds, reconstruction_error=r.reconstruction_error,
        features=[FeatureContributionOut(source_feature=f.source_feature, raw_value=f.raw_value,
                                         shap_value=f.shap_value, direction=f.direction,  # type: ignore[arg-type]
                                         is_engineered=f.is_engineered) for f in features],
        interpretation=r.interpretation, model_version=r.model_version)


def to_business(customer_id: str | None, r: BusinessResult) -> BusinessResponse:
    return BusinessResponse(
        customer_id=customer_id, churn_probability=r.churn_probability, risk_band=r.risk_band, currency=r.currency,
        clv=r.clv, value_at_risk=r.value_at_risk,
        intervention_decision=r.intervention_decision,  # type: ignore[arg-type]
        recommended_action_id=r.recommended_action_id, recommended_action=r.recommended_action,
        action_cost=r.action_cost, action_success_rate=r.action_success_rate, expected_benefit=r.expected_benefit,
        expected_cost=r.expected_cost, expected_net_benefit=r.expected_net_benefit,
        decision_reasons=[DecisionReasonOut(code=d.code, values=dict(d.values)) for d in r.decision_reasons],
        decision_reason_messages=list(r.decision_reason_messages),
        action_evaluations=[ActionEvaluationOut(
            action_id=a.action_id, name=a.name, cost=a.cost, success_rate=a.success_rate, eligible=a.eligible,
            ineligible_reason=a.ineligible_reason, expected_benefit=a.expected_benefit,
            expected_cost=a.expected_cost, expected_net_benefit=a.expected_net_benefit)
            for a in r.action_evaluations],
        explanation=BusinessExplanationOut(model_explanation=r.explanation.model_explanation,
                                           business_decision=r.explanation.business_decision,
                                           disclaimer=r.explanation.disclaimer),
        notice=r.notice)


def to_segment(customer_id: str | None, r: SegmentResult) -> SegmentResponse:
    return SegmentResponse(
        customer_id=customer_id, segment_id=r.segment_id, segment_name=r.segment_name,
        distance_to_centroid=r.distance_to_centroid, segment_model_version=r.model_version,
        segment_count=r.segment_count, segment_customer_count=r.customer_count,
        segment_priority_rank=r.priority_rank, segment_priority_tier=r.priority_tier, note=r.note)
