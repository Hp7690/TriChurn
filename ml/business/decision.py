"""Deterministic, explainable intervention decision.

INTERVENE  iff  churn_probability >= min_churn_probability
            AND clv >= min_customer_value
            AND the best eligible action has ENB > min_expected_net_benefit.
Otherwise DO_NOT_INTERVENE, and ``no_action`` is the recommendation. Every failed (or passed) check is returned as a
structured reason; wording is rendered separately (see ``formatting``).
"""
from __future__ import annotations

from collections.abc import Mapping
from typing import Any

from ml.business.retention import best_by_enb, evaluate_actions, select_best_action
from ml.business.schemas import (
    DO_NOT_INTERVENE,
    INTERVENE,
    MODEL_THRESHOLD,
    NO_ACTION_ID,
    ActionEvaluation,
    DecisionReason,
    DecisionResult,
    InterventionPolicy,
    ResolvedPolicy,
    RetentionAction,
)
from ml.business.validation import require_non_negative, require_probability
from ml.errors import BusinessInputError


def resolve_policy(policy: InterventionPolicy, model_threshold: float | None = None) -> ResolvedPolicy:
    """Replace the ``model_threshold`` sentinel by the locked model's operating threshold."""
    mcp = policy.min_churn_probability
    if mcp == MODEL_THRESHOLD:
        if model_threshold is None:
            raise BusinessInputError(
                "policy.min_churn_probability is 'model_threshold' but no model_threshold was supplied.")
        mcp = require_probability(model_threshold, "model_threshold")
    return ResolvedPolicy(float(mcp), policy.min_customer_value, policy.min_expected_net_benefit,
                          policy.max_action_cost)


def decide(clv: Any, churn_probability: Any, actions: Mapping[str, RetentionAction],
           policy: ResolvedPolicy) -> DecisionResult:
    """Evaluate every enabled action, apply the policy, and return the decision with its reasons."""
    clv_v = require_non_negative(clv, "clv")
    p = require_probability(churn_probability)
    evaluations = evaluate_actions(actions, clv_v, p, policy.max_action_cost)
    no_action = next(e for e in evaluations if e.action.action_id == NO_ACTION_ID)
    best = select_best_action(evaluations, policy.min_expected_net_benefit)

    prob_ok = p >= policy.min_churn_probability
    value_ok = clv_v >= policy.min_customer_value
    benefit_ok = best is not None

    if prob_ok and value_ok and benefit_ok:
        return DecisionResult(INTERVENE, best, best, _intervene_reasons(p, clv_v, best, policy), policy, evaluations)

    reasons: list[DecisionReason] = []
    if not prob_ok:
        reasons.append(DecisionReason("CHURN_PROBABILITY_BELOW_MINIMUM",
                                      {"churn_probability": p, "minimum": policy.min_churn_probability}))
    if not value_ok:
        reasons.append(DecisionReason("CUSTOMER_VALUE_BELOW_MINIMUM",
                                      {"clv": clv_v, "minimum": policy.min_customer_value}))
    if not benefit_ok:
        top = best_by_enb(evaluations)
        reasons.append(DecisionReason("NO_ACTION_WITH_ENB_ABOVE_MINIMUM", {
            "minimum": policy.min_expected_net_benefit,
            "best_action_id": None if top is None else top.action.action_id,
            "best_expected_net_benefit": None if top is None else top.enb.expected_net_benefit}))
    return DecisionResult(DO_NOT_INTERVENE, no_action, best, tuple(reasons), policy, evaluations)


def _intervene_reasons(p: float, clv: float, best: ActionEvaluation,
                       policy: ResolvedPolicy) -> tuple[DecisionReason, ...]:
    return (
        DecisionReason("CHURN_PROBABILITY_AT_OR_ABOVE_MINIMUM",
                       {"churn_probability": p, "minimum": policy.min_churn_probability}),
        DecisionReason("CUSTOMER_VALUE_AT_OR_ABOVE_MINIMUM", {"clv": clv, "minimum": policy.min_customer_value}),
        DecisionReason("POSITIVE_EXPECTED_NET_BENEFIT", {
            "action_id": best.action.action_id, "expected_net_benefit": best.enb.expected_net_benefit,
            "minimum": policy.min_expected_net_benefit}),
        DecisionReason("ACTION_JUSTIFIED_UNDER_ASSUMPTIONS", {
            "action_id": best.action.action_id, "success_rate": best.enb.action_success_rate,
            "cost": best.enb.action_cost}),
    )
