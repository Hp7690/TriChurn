"""Value at Risk and Expected Net Benefit, one small auditable function per formula.

    value_at_risk        = CLV * churn_probability
    expected_benefit     = value_at_risk * action_success_rate
    expected_cost        = action_cost                     (paid with certainty once the action is taken)
    expected_net_benefit = expected_benefit - expected_cost
                         = CLV * churn_probability * action_success_rate - action_cost

Value at Risk is an EXPECTED-RISK figure: the model's probability times an assumed value. It is not a causal
estimate. ``action_success_rate`` is a configured business assumption, not a measured treatment effect.
"""
from __future__ import annotations

from typing import Any

from ml.business.schemas import EnbBreakdown
from ml.business.validation import require_non_negative, require_probability, require_rate


def value_at_risk(clv: Any, churn_probability: Any) -> float:
    """Expected customer value exposed to churn: CLV * P(churn)."""
    return require_non_negative(clv, "clv") * require_probability(churn_probability)


def expected_benefit(var: float, success_rate: Any) -> float:
    """Expected value retained under the ASSUMED success rate: value_at_risk * success_rate."""
    return var * require_rate(success_rate, "action_success_rate")


def expected_cost(action_cost: Any) -> float:
    """Cost of the action for one customer."""
    return require_non_negative(action_cost, "action_cost")


def compute_enb(clv: Any, churn_probability: Any, action_success_rate: Any, action_cost: Any) -> EnbBreakdown:
    """All ENB components for one (customer, action) pair."""
    clv_v = require_non_negative(clv, "clv")
    p = require_probability(churn_probability)
    var = value_at_risk(clv_v, p)
    benefit = expected_benefit(var, action_success_rate)
    cost = expected_cost(action_cost)
    return EnbBreakdown(clv=clv_v, churn_probability=p, value_at_risk=var,
                        action_success_rate=float(action_success_rate), action_cost=cost,
                        expected_benefit=benefit, expected_cost=cost, expected_net_benefit=benefit - cost)
