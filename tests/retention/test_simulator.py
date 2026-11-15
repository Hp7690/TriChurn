from __future__ import annotations

import pytest

from ml.business.enb import compute_enb
from retention.config import load_retention_config
from retention.errors import RetentionInputError
from retention.prioritization import PriorityIndex
from retention.simulator import ScenarioSpec, compare_scenarios, simulate_scenario
from tests.retention.support import make_portfolio

PF = make_portfolio(120)
IDX = PriorityIndex(PF, load_retention_config().priority)
ACTION = "discount_offer"


def _sim(**kw):
    return simulate_scenario(ScenarioSpec(action_id=ACTION, **kw), PF, IDX, 10000)


def test_totals_match_the_phase4_enb_formula_per_customer():
    result = _sim(decision_filter="any")
    action = next(a for a in PF.action_catalogue if a.action_id == ACTION)
    eligible = [c for c in PF.customers
                if next(o for o in c.options if o.action_id == ACTION).eligible]
    benefit = cost = 0.0
    for c in eligible:
        enb = compute_enb(c.clv, c.churn_probability, action.success_rate, action.cost)
        benefit += enb.expected_benefit
        cost += enb.expected_cost
    assert result.eligible_customers == len(eligible)
    assert abs(result.estimated_retained_revenue - benefit) < 0.05
    assert abs(result.total_cost - cost) < 0.05
    assert abs(result.estimated_net_benefit - (benefit - cost)) < 0.1


def test_roi_is_net_benefit_over_cost():
    r = _sim()
    assert r.total_cost > 0
    assert abs(r.estimated_roi - r.estimated_net_benefit / r.total_cost) < 1e-3


def test_overrides_change_only_the_assumptions_and_are_labelled():
    base, over = _sim(), _sim(success_rate_override=0.5, cost_override=1.0)
    assert (base.cost_source, base.success_rate_source) == ("phase4_config", "phase4_config")
    assert (over.cost_source, over.success_rate_source) == ("scenario_override", "scenario_override")
    assert over.estimated_retained_revenue > base.estimated_retained_revenue
    assert over.total_cost < base.total_cost
    assert over.label == "ESTIMATE" and "not measured" in over.note


def test_phase4_eligibility_is_respected():
    result = simulate_scenario(ScenarioSpec(action_id="personalized_offer", decision_filter="any"), PF, IDX, 10000)
    assert result.excluded_ineligible > 0
    assert result.eligible_customers + result.excluded_ineligible == result.targeted_customers


def test_targeting_filters_and_top_n():
    top = _sim(top_n=5)
    assert top.targeted_customers == 5
    bands = _sim(risk_bands=("CRITICAL",), decision_filter="any")
    assert bands.targeted_customers == sum(1 for c in PF.customers if c.risk_band == "CRITICAL")
    ids = [c.customer_id for c in PF.customers[:3]]
    assert _sim(customer_ids=tuple(ids), decision_filter="any").targeted_customers == 3


def test_top_n_uses_priority_order_for_explicit_customer_ids():
    ranked = [
        entry.customer
        for entry in IDX.entries
        if next(option for option in entry.customer.options if option.action_id == ACTION).eligible
    ]
    selected_ids = tuple(customer.customer_id for customer in reversed(ranked[:10]))

    result = _sim(customer_ids=selected_ids, top_n=3, decision_filter="any")

    assert result.targeted_customers == 3
    assert result.total_value_at_risk == round(sum(customer.value_at_risk for customer in ranked[:3]), 2)


def test_empty_target_set_gives_zeroes_and_no_roi():
    r = _sim(min_churn_probability=1.0, risk_bands=("LOW",))
    assert r.targeted_customers == 0 and r.total_cost == 0 and r.estimated_roi is None
    assert r.cost_per_expected_retained_customer is None


def test_compare_scenarios_reports_best_by_net_benefit_and_roi():
    specs = [ScenarioSpec(action_id="discount_offer"), ScenarioSpec(action_id="loyalty_offer"),
             ScenarioSpec(action_id="retention_email", top_n=10)]
    cmp = compare_scenarios(specs, PF, IDX, 10, 10000)
    assert len(cmp.results) == 3 and cmp.label == "ESTIMATE"
    nets = [r.estimated_net_benefit for r in cmp.results]
    assert nets[cmp.best_by_net_benefit_index] == max(nets)
    rois = {i: r.estimated_roi for i, r in enumerate(cmp.results) if r.estimated_roi is not None}
    assert rois[cmp.best_by_roi_index] == max(rois.values())


def test_scenarios_never_modify_the_portfolio():
    before = [(c.customer_id, c.value_at_risk, c.expected_net_benefit) for c in PF.customers]
    _sim(success_rate_override=0.9)
    assert before == [(c.customer_id, c.value_at_risk, c.expected_net_benefit) for c in PF.customers]


@pytest.mark.parametrize("spec", [
    ScenarioSpec(action_id="no_action"),
    ScenarioSpec(action_id="does_not_exist"),
    ScenarioSpec(action_id=ACTION, success_rate_override=1.5),
    ScenarioSpec(action_id=ACTION, success_rate_override=float("nan")),
    ScenarioSpec(action_id=ACTION, cost_override=-1.0),
    ScenarioSpec(action_id=ACTION, cost_override=float("inf")),
    ScenarioSpec(action_id=ACTION, min_churn_probability=2.0),
    ScenarioSpec(action_id=ACTION, top_n=0),
    ScenarioSpec(action_id=ACTION, decision_filter="maybe"),
    ScenarioSpec(action_id=ACTION, customer_ids=("NOPE-1",)),
])
def test_invalid_scenarios_are_rejected(spec):
    with pytest.raises(RetentionInputError):
        simulate_scenario(spec, PF, IDX, 10000)


def test_limits_on_scenarios_and_targets():
    with pytest.raises(RetentionInputError):
        compare_scenarios([], PF, IDX, 10, 10000)
    with pytest.raises(RetentionInputError):
        compare_scenarios([ScenarioSpec(action_id=ACTION)] * 3, PF, IDX, 2, 10000)
    with pytest.raises(RetentionInputError):
        simulate_scenario(ScenarioSpec(action_id=ACTION, decision_filter="any"), PF, IDX, 5)
