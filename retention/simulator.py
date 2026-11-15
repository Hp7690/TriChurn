"""Retention campaign what-if simulator.

For each scenario (an action applied to a targeted set of customers), using the Phase 4 formulas per customer:

    estimated_retained_revenue = sum( value_at_risk_i x success_rate )        # = Phase 4 expected benefit
    total_cost                 = action_cost x eligible_customers
    estimated_net_benefit      = estimated_retained_revenue - total_cost
    estimated_roi              = estimated_net_benefit / total_cost           (None when cost is 0)
    expected_retained_customers = sum( churn_probability_i x success_rate )

Action cost and success rate default to ``configs/business.yaml`` (Phase 4); a scenario may override them to
explore ASSUMPTIONS. Every figure is an ESTIMATE under those assumptions, never an observed campaign result.
"""
from __future__ import annotations

import math
from collections.abc import Sequence
from dataclasses import dataclass

from retention import ESTIMATE_NOTE
from retention.errors import RetentionInputError
from retention.models import INTERVENE, NO_ACTION_ID, ActionOption, Portfolio, ScoredCustomer
from retention.prioritization import PriorityIndex

LABEL = "ESTIMATE"
SOURCE_PHASE4 = "phase4_config"
SOURCE_OVERRIDE = "scenario_override"


@dataclass(frozen=True)
class ScenarioSpec:
    action_id: str
    name: str | None = None
    cost_override: float | None = None
    success_rate_override: float | None = None
    decision_filter: str = "intervene"            # "intervene" (Phase 4 candidates) or "any"
    risk_bands: tuple[str, ...] = ()
    segment_ids: tuple[int, ...] = ()
    min_churn_probability: float | None = None
    top_n: int | None = None                      # best N by priority rank among the matching customers
    customer_ids: tuple[str, ...] = ()


@dataclass(frozen=True)
class ScenarioResult:
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
    label: str = LABEL
    note: str = ESTIMATE_NOTE


@dataclass(frozen=True)
class ScenarioComparison:
    results: tuple[ScenarioResult, ...]
    best_by_net_benefit_index: int | None      # position in ``results``
    best_by_roi_index: int | None
    label: str = LABEL
    note: str = ESTIMATE_NOTE


def _finite(value: float | None, name: str, low: float, high: float | None = None) -> None:
    if value is None:
        return
    if isinstance(value, bool) or not math.isfinite(value) or value < low or (high is not None and value > high):
        raise RetentionInputError(f"{name} is out of range.")


def _action(portfolio: Portfolio, action_id: str) -> ActionOption:
    if action_id == NO_ACTION_ID:
        raise RetentionInputError("'no_action' cannot be simulated as a campaign.")
    for option in portfolio.action_catalogue:
        if option.action_id == action_id:
            if not option.eligible:        # in the catalogue ``eligible`` carries the Phase 4 ``enabled`` flag
                raise RetentionInputError(f"Action '{action_id}' is disabled in the Phase 4 configuration.")
            return option
    raise RetentionInputError(f"Unknown action '{action_id}'.")


def _target(spec: ScenarioSpec, portfolio: Portfolio, index: PriorityIndex, limit: int) -> list[ScoredCustomer]:
    if spec.decision_filter not in ("intervene", "any"):
        raise RetentionInputError("decision_filter must be 'intervene' or 'any'.")
    _finite(spec.min_churn_probability, "min_churn_probability", 0.0, 1.0)
    if spec.top_n is not None and spec.top_n < 1:
        raise RetentionInputError("top_n must be at least 1.")
    if spec.customer_ids:
        unknown = [i for i in spec.customer_ids if portfolio.get(i) is None]
        if unknown:
            raise RetentionInputError(f"{len(unknown)} customer id(s) are not in the scored portfolio.")
        chosen = [portfolio.index[i] for i in dict.fromkeys(spec.customer_ids)]
    else:
        chosen = [e.customer for e in index.entries]          # already in priority order
    matches = [c for c in chosen
               if (spec.decision_filter == "any" or c.decision == INTERVENE)
               and (not spec.risk_bands or c.risk_band in spec.risk_bands)
               and (not spec.segment_ids or c.segment_id in spec.segment_ids)
               and (spec.min_churn_probability is None or c.churn_probability >= spec.min_churn_probability)]
    if spec.top_n is not None:
        matching_ids = {customer.customer_id for customer in matches}
        matches = [entry.customer for entry in index.entries if entry.customer.customer_id in matching_ids]
        matches = matches[:spec.top_n]
    if len(matches) > limit:
        raise RetentionInputError(f"The scenario targets more than {limit} customers.")
    return matches


def simulate_scenario(spec: ScenarioSpec, portfolio: Portfolio, index: PriorityIndex, max_targets: int,
                      default_name: str = "Scenario") -> ScenarioResult:
    action = _action(portfolio, spec.action_id)
    _finite(spec.cost_override, "cost_override", 0.0)
    _finite(spec.success_rate_override, "success_rate_override", 0.0, 1.0)
    cost = action.cost if spec.cost_override is None else float(spec.cost_override)
    rate = action.success_rate if spec.success_rate_override is None else float(spec.success_rate_override)
    targets = _target(spec, portfolio, index, max_targets)

    eligible: list[ScoredCustomer] = []
    for customer in targets:
        option = next((o for o in customer.options if o.action_id == spec.action_id), None)
        if option is not None and option.eligible:            # Phase 4 eligibility (e.g. minimum CLV) is respected
            eligible.append(customer)
    value_at_risk = math.fsum(c.value_at_risk for c in eligible)
    retained = value_at_risk * rate
    total_cost = cost * len(eligible)
    net = retained - total_cost
    expected_customers = math.fsum(c.churn_probability for c in eligible) * rate
    return ScenarioResult(
        name=spec.name or default_name, action_id=action.action_id, action_name=action.name,
        cost_per_customer=cost, cost_source=SOURCE_PHASE4 if spec.cost_override is None else SOURCE_OVERRIDE,
        success_rate=rate,
        success_rate_source=SOURCE_PHASE4 if spec.success_rate_override is None else SOURCE_OVERRIDE,
        targeted_customers=len(targets), eligible_customers=len(eligible),
        excluded_ineligible=len(targets) - len(eligible),
        total_value_at_risk=round(value_at_risk, 2), total_cost=round(total_cost, 2),
        estimated_retained_revenue=round(retained, 2), estimated_net_benefit=round(net, 2),
        estimated_roi=None if total_cost == 0 else round(net / total_cost, 4),
        expected_retained_customers=round(expected_customers, 2),
        cost_per_expected_retained_customer=(
            None if expected_customers == 0 else round(total_cost / expected_customers, 2)))


def compare_scenarios(specs: Sequence[ScenarioSpec], portfolio: Portfolio, index: PriorityIndex,
                      max_scenarios: int, max_targets: int) -> ScenarioComparison:
    if not specs:
        raise RetentionInputError("At least one scenario is required.")
    if len(specs) > max_scenarios:
        raise RetentionInputError(f"At most {max_scenarios} scenarios can be compared at once.")
    results = tuple(simulate_scenario(s, portfolio, index, max_targets, f"Scenario {i + 1}")
                    for i, s in enumerate(specs))
    best_net = max(range(len(results)), key=lambda i: (results[i].estimated_net_benefit, -i))
    with_cost = [i for i, r in enumerate(results) if r.estimated_roi is not None]
    best_roi = max(with_cost, key=lambda i: (results[i].estimated_roi or 0.0, -i)) if with_cost else None
    return ScenarioComparison(results, best_net, best_roi)
