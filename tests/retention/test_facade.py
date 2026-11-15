from __future__ import annotations

import pytest

from retention.campaign_store import CampaignStore, NewOutcome
from retention.config import load_retention_config
from retention.errors import (
    PortfolioUnavailableError,
    RetentionInputError,
    RetentionNotFoundError,
)
from retention.facade import RetentionFacade
from retention.models import INTERVENE
from retention.prioritization import PriorityFilter
from retention.recommendation import Driver
from retention.simulator import ScenarioSpec
from tests.retention.support import StaticProvider, make_portfolio

PF = make_portfolio(100)


def _facade(portfolio=PF, error=None):
    return RetentionFacade(StaticProvider(portfolio, error), CampaignStore(":memory:"), load_retention_config())


def test_summary_is_consistent_with_the_portfolio():
    f = _facade()
    s = f.summary()
    assert s.total_customers == 100
    assert abs(s.revenue_at_risk - sum(c.value_at_risk for c in PF.customers)) < 0.5
    assert s.intervention_candidates == sum(1 for c in PF.customers if c.decision == INTERVENE)
    assert sum(b.customers for b in s.by_risk_band) == 100 and sum(g.customers for g in s.by_segment) == 100
    assert sum(c.customers for c in s.recommended_campaigns) == s.intervention_candidates
    assert abs(s.estimated_net_benefit - (s.estimated_retained_revenue - s.estimated_total_cost)) < 0.1
    assert "ASSUMED" in s.note and "not a probability" in s.score_note
    assert len(s.top_priorities) <= 10 and s.top_priorities[0].rank == 1


def test_recommendation_uses_phase4_decision_and_degrades_without_drivers():
    f = _facade()
    candidate = next(c for c in PF.customers if c.decision == INTERVENE)
    rec = f.recommendation(candidate.customer_id)
    assert rec.primary_action.action_id == candidate.recommended_action_id
    assert rec.explainability_available is False and rec.drivers == ()
    assert rec.causal_claim is False and rec.uplift_available is False
    assert rec.reasons and "heuristic" in rec.basis
    assert all(a.expected_net_benefit <= rec.primary_action.expected_net_benefit for a in rec.alternatives)

    monitor = next(c for c in PF.customers if c.decision != INTERVENE)
    assert f.recommendation(monitor.customer_id).primary_action is None


def test_recommendation_includes_supplied_drivers():
    f = _facade()
    cid = PF.customers[0].customer_id
    rec = f.recommendation(cid, [Driver("Contract", "Month-to-month", 0.4, "increases_churn")])
    assert rec.explainability_available and rec.drivers[0].feature == "Contract"
    assert "not show that" in rec.explainability_note


def test_unknown_customer():
    f = _facade()
    with pytest.raises(RetentionNotFoundError):
        f.recommendation("nobody")
    with pytest.raises(RetentionNotFoundError):
        f.customer_features("nobody")


def test_priorities_return_reasons_for_each_item():
    f = _facade()
    page, reasons = f.priorities(PriorityFilter(), "rank", False, 1, 5)
    assert len(page.items) == 5 and all(reasons[e.customer.customer_id] for e in page.items)


def test_campaign_lifecycle_with_phase4_snapshots():
    f = _facade()
    campaign = f.create_campaign("Win-back", "discount_offer", "2025-03-01", False, None)
    eligible = [c for c in PF.customers if next(o for o in c.options if o.action_id == "discount_offer").eligible]
    ids = [c.customer_id for c in eligible[:3]]
    report = f.assign(campaign.campaign_id, ids + ["ghost"], "unspecified")
    assert (report.requested, report.assigned) == (4, 3) and report.unknown_customer_ids == ("ghost",)
    rows = f._store.assignments(campaign.campaign_id)                      # noqa: SLF001
    opt = next(o for o in eligible[0].options if o.action_id == "discount_offer")
    assert rows[0].estimated_cost == opt.cost and rows[0].estimated_benefit == opt.expected_benefit
    assert f.assign(campaign.campaign_id, ids[:1], "unspecified").already_assigned_ids == (ids[0],)

    out = f.record_outcomes(campaign.campaign_id, [NewOutcome(ids[0], "retained", 50.0, 400.0)])
    assert out.recorded == 1
    m = f.campaign_metrics(campaign.campaign_id)
    assert m.assigned == 3 and m.outcomes_recorded == 1 and m.actual_retained_revenue == 400.0
    assert f.analytics().total_assigned == 3


def test_control_group_assignments_carry_no_estimated_cost_or_benefit():
    f = _facade()
    campaign = f.create_campaign("Holdout", "loyalty_offer", "2025-03-01", True, None)
    f.assign(campaign.campaign_id, [PF.customers[0].customer_id], "control")
    row = f._store.assignments(campaign.campaign_id)[0]                      # noqa: SLF001
    assert (row.assignment_group, row.estimated_cost, row.estimated_benefit) == ("control", 0.0, 0.0)


def test_ineligible_customers_are_reported_not_assigned():
    f = _facade()
    campaign = f.create_campaign("VIP", "personalized_offer", "2025-03-01", False, None)
    low = next(c for c in PF.customers
               if not next(o for o in c.options if o.action_id == "personalized_offer").eligible)
    report = f.assign(campaign.campaign_id, [low.customer_id], "unspecified")
    assert report.assigned == 0 and report.ineligible_customer_ids == (low.customer_id,)


@pytest.mark.parametrize("action", ["no_action", "ghost", "", "DISCOUNT_OFFER"])
def test_campaign_requires_an_enabled_phase4_action(action):
    with pytest.raises(RetentionInputError):
        _facade().create_campaign("x", action, "2025-03-01", False, None)


def test_request_size_limits():
    f = _facade()
    campaign = f.create_campaign("x", "discount_offer", "2025-03-01", False, None)
    cap = load_retention_config().campaigns.max_customers_per_request
    with pytest.raises(RetentionInputError):
        f.assign(campaign.campaign_id, [f"id{i}" for i in range(cap + 1)], "unspecified")
    with pytest.raises(RetentionInputError):
        f.assign(campaign.campaign_id, [], "unspecified")
    with pytest.raises(RetentionInputError):
        f.assign(campaign.campaign_id, ["a"], "vip")
    with pytest.raises(RetentionInputError):
        f.record_outcomes(campaign.campaign_id, [])


def test_empty_portfolio_end_to_end():
    from dataclasses import replace

    f = _facade(replace(PF, customers=(), index={}))
    s = f.summary()
    assert s.total_customers == 0 and s.revenue_at_risk == 0 and s.estimated_roi is None and s.top_priorities == ()
    assert f.priorities(PriorityFilter(), "rank", False, 1, 10)[0].total == 0
    result = f.simulate([ScenarioSpec(action_id="discount_offer")])
    assert result.results[0].targeted_customers == 0


def test_portfolio_failure_propagates_but_campaign_reads_still_work():
    f = _facade(error=PortfolioUnavailableError("phase2_model_missing"))
    with pytest.raises(PortfolioUnavailableError):
        f.summary()
    assert f.campaigns() == [] and f.analytics().total_assigned == 0
    readiness = f.uplift_readiness()                                    # works without the dataset
    assert readiness.status == "NOT_READY"


def test_portfolio_is_loaded_once_and_the_ranking_is_cached():
    provider = StaticProvider(PF)
    f = RetentionFacade(provider, CampaignStore(":memory:"), load_retention_config())
    first = f.index()
    assert f.index() is first
