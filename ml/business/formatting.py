"""Presentation only. Business calculations never call this; it turns numbers and reason codes into text.

Wording rule: success rates are ASSUMPTIONS. Text says "under the configured success-rate assumption ... estimated",
never that an action will prevent churn.
"""
from __future__ import annotations

from ml.business.schemas import CurrencyConfig, CustomerBusinessProfile, DecisionReason


def format_money(amount: float, currency: CurrencyConfig) -> str:
    sign = "-" if amount < 0 else ""
    return f"{sign}{currency.symbol}{abs(amount):,.2f}"


def render_reason(reason: DecisionReason, currency: CurrencyConfig) -> str:
    v, m = reason.values, (lambda x: format_money(x, currency))
    code = reason.code
    if code == "CHURN_PROBABILITY_AT_OR_ABOVE_MINIMUM":
        return f"Churn probability {v['churn_probability']:.2f} is at or above the minimum {v['minimum']:.2f}."
    if code == "CHURN_PROBABILITY_BELOW_MINIMUM":
        return f"Churn probability {v['churn_probability']:.2f} is below the minimum {v['minimum']:.2f}."
    if code == "CUSTOMER_VALUE_AT_OR_ABOVE_MINIMUM":
        return f"Customer value (CLV) {m(v['clv'])} is at or above the minimum {m(v['minimum'])}."
    if code == "CUSTOMER_VALUE_BELOW_MINIMUM":
        return f"Customer value (CLV) {m(v['clv'])} is below the minimum {m(v['minimum'])}."
    if code == "POSITIVE_EXPECTED_NET_BENEFIT":
        return (f"Expected net benefit of '{v['action_id']}' is {m(v['expected_net_benefit'])}, above the minimum "
                f"{m(v['minimum'])}.")
    if code == "ACTION_JUSTIFIED_UNDER_ASSUMPTIONS":
        return (f"Under the configured success-rate assumption ({v['success_rate']:.2f}) and cost {m(v['cost'])}, "
                f"'{v['action_id']}' is estimated to be economically justified.")
    if code == "NO_ACTION_WITH_ENB_ABOVE_MINIMUM":
        if v["best_action_id"] is None:
            return "No eligible retention action is available."
        return (f"No eligible action has expected net benefit above {m(v['minimum'])} under the configured "
                f"assumptions (best: '{v['best_action_id']}' at {m(v['best_expected_net_benefit'])}).")
    return code


def format_profile(profile: CustomerBusinessProfile, currency: CurrencyConfig) -> str:
    """Human-readable summary of one profile (same fields as ``to_dict``)."""
    m = lambda x: format_money(x, currency)  # noqa: E731
    lines = [
        f"Customer ID: {profile.customer_id}",
        f"Churn Probability: {profile.churn_probability:.2f}   Risk Band: {profile.risk_band}",
        f"CLV: {m(profile.clv)}   Value at Risk: {m(profile.value_at_risk)}",
        f"Recommended Action: {profile.recommended_action}",
        f"Action Cost: {m(profile.action_cost)}   Assumed Success Rate: {profile.action_success_rate:.2f}",
        f"Expected Benefit: {m(profile.expected_benefit)}   Expected Net Benefit: {m(profile.expected_net_benefit)}",
        f"Decision: {profile.intervention_decision}",
        "Reasons:", *[f"- {msg}" for msg in profile.decision_reason_messages],
    ]
    return "\n".join(lines)
