from __future__ import annotations

from datetime import UTC, datetime

from retention.analytics import build_overview, campaign_metrics
from retention.campaign_store import CampaignStore, NewAssignment, NewOutcome
from retention.config import load_retention_config
from retention.uplift_readiness import assess

NOW = datetime(2025, 3, 1, tzinfo=UTC)
UP = load_retention_config().uplift


def _store_with_campaign(randomized=False):
    store = CampaignStore(":memory:")
    c = store.create_campaign("c", "discount_offer", "2025-03-01", randomized, None, now=NOW)
    return store, c


def test_empty_store_gives_empty_analytics_not_fabricated_numbers():
    overview = build_overview([], [])
    assert overview.campaigns == () and overview.total_assigned == 0
    assert overview.total_actual_cost is None and overview.total_actual_retained_revenue is None


def test_campaign_without_outcomes_has_no_actuals_or_rates():
    store, c = _store_with_campaign()
    store.assign(c.campaign_id, [NewAssignment("A", 60.0, 100.0, 0.6), NewAssignment("B", 60.0, 50.0, 0.4)])
    m = campaign_metrics(c, store.assignments(c.campaign_id))
    assert (m.assigned, m.outcomes_recorded) == (2, 0)
    assert m.observed_retention_rate is None and m.outcome_coverage == 0.0
    assert m.actual_cost is None and m.actual_retained_revenue is None and m.actual_roi is None
    assert (m.estimated_cost, m.estimated_benefit) == (120.0, 150.0)


def test_estimated_and_actual_are_kept_separate():
    store, c = _store_with_campaign()
    store.assign(c.campaign_id, [NewAssignment("A", 60.0, 100.0, 0.6), NewAssignment("B", 60.0, 50.0, 0.4)])
    store.record_outcomes(c.campaign_id, [NewOutcome("A", "retained", 70.0, 500.0), NewOutcome("B", "churned", 65.0)])
    m = campaign_metrics(c, store.assignments(c.campaign_id))
    assert (m.estimated_cost, m.estimated_benefit) == (120.0, 150.0)          # unchanged by outcomes
    assert m.actual_cost == 135.0 and m.actual_retained_revenue == 500.0
    assert m.actual_net_benefit == 365.0 and abs(m.actual_roi - 365.0 / 135.0) < 1e-3
    assert (m.retained, m.churned, m.observed_retention_rate, m.outcome_coverage) == (1, 1, 0.5, 1.0)
    assert "no uplift is claimed" in m.note


def test_net_and_roi_absent_when_only_one_actual_exists():
    store, c = _store_with_campaign()
    store.assign(c.campaign_id, [NewAssignment("A", 60.0, 100.0, 0.6)])
    store.record_outcomes(c.campaign_id, [NewOutcome("A", "churned", actual_cost=60.0)])
    m = campaign_metrics(c, store.assignments(c.campaign_id))
    assert m.actual_cost == 60.0 and m.actual_retained_revenue is None
    assert m.actual_net_benefit is None and m.actual_roi is None


def test_overview_totals_across_campaigns():
    store, a = _store_with_campaign()
    b = store.create_campaign("d", "loyalty_offer", "2025-03-02", False, None, now=NOW)
    store.assign(a.campaign_id, [NewAssignment("A", 10.0, 20.0, 0.5)])
    store.assign(b.campaign_id, [NewAssignment("B", 5.0, 8.0, 0.5)])
    o = build_overview(store.list_campaigns(), store.assignments())
    assert o.total_assigned == 2 and o.total_estimated_cost == 15.0 and o.total_estimated_benefit == 28.0


# ------------------------------------------------------------------------------------- uplift readiness
def test_not_ready_without_any_campaign_data():
    r = assess(["customerID", "tenure", "Churn"], [], [], UP)
    assert r.ready is False and r.status == "NOT_READY"
    assert r.dataset_treatment_columns == ()
    assert {c.code for c in r.checks if not c.passed} >= {"treatment_group_size", "control_group_size"}
    assert "No uplift model exists" in r.note and len(r.requirements) >= 4


def test_dataset_columns_that_look_like_treatment_are_reported():
    r = assess(["customerID", "campaign_group", "OfferAccepted"], [], [], UP)
    assert set(r.dataset_treatment_columns) == {"campaign_group", "OfferAccepted"}
    assert r.ready is False                                     # columns alone are never enough


def test_uninspectable_dataset_is_reported_honestly():
    r = assess(None, [], [], UP)
    check = next(c for c in r.checks if c.code == "dataset_has_treatment_columns")
    assert not check.passed and "could not be inspected" in check.detail


def test_treatment_only_data_is_not_ready():
    store, c = _store_with_campaign(randomized=True)
    store.assign(c.campaign_id, [NewAssignment(f"T{i}", 1.0, 1.0, 0.5, "treatment") for i in range(600)])
    r = assess([], store.list_campaigns(), store.assignments(), UP)
    assert r.ready is False and r.treatment_assignments == 600 and r.control_assignments == 0


def test_ready_only_with_randomised_balanced_arms_and_outcomes():
    store, c = _store_with_campaign(randomized=True)
    store.assign(c.campaign_id, [NewAssignment(f"T{i}", 1.0, 1.0, 0.5, "treatment") for i in range(500)])
    store.assign(c.campaign_id, [NewAssignment(f"C{i}", 0.0, 0.0, 0.5, "control") for i in range(500)])
    store.record_outcomes(c.campaign_id, [NewOutcome(f"T{i}", "retained") for i in range(500)])
    store.record_outcomes(c.campaign_id, [NewOutcome(f"C{i}", "churned") for i in range(500)])
    ready = assess([], store.list_campaigns(), store.assignments(), UP)
    assert ready.ready is True and ready.status == "READY_FOR_FEASIBILITY_REVIEW"

    not_random, nc = _store_with_campaign(randomized=False)
    not_random.assign(nc.campaign_id, [NewAssignment(f"T{i}", 1.0, 1.0, 0.5, "treatment") for i in range(500)])
    not_random.assign(nc.campaign_id, [NewAssignment(f"C{i}", 0.0, 0.0, 0.5, "control") for i in range(500)])
    not_random.record_outcomes(nc.campaign_id, [NewOutcome(f"T{i}", "retained") for i in range(500)])
    not_random.record_outcomes(nc.campaign_id, [NewOutcome(f"C{i}", "churned") for i in range(500)])
    assert assess([], not_random.list_campaigns(), not_random.assignments(), UP).ready is False
