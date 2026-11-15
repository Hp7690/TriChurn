from __future__ import annotations

import pytest

from retention.config import load_retention_config
from retention.errors import RetentionInputError
from retention.models import INTERVENE
from retention.prioritization import TIER_MONITOR, PriorityFilter, PriorityIndex, explain_priority
from tests.retention.support import make_portfolio

PF = make_portfolio(80)
CFG = load_retention_config().priority
IDX = PriorityIndex(PF, CFG)


def test_every_customer_ranked_once_in_a_total_order():
    ranks = [e.rank for e in IDX.entries]
    assert ranks == list(range(1, len(PF.customers) + 1))
    assert {e.customer.customer_id for e in IDX.entries} == {c.customer_id for c in PF.customers}


def test_intervention_candidates_come_first_then_score_descending():
    seen_monitor = False
    previous = None
    for e in IDX.entries:
        candidate = e.customer.decision == INTERVENE
        assert not (seen_monitor and candidate)
        if not candidate:
            seen_monitor = True
        if previous is not None and previous.customer.decision == e.customer.decision:
            assert previous.score >= e.score
        previous = e


def test_scores_are_bounded_and_not_probabilities():
    assert all(0.0 <= e.score <= 100.0 for e in IDX.entries)
    assert any(e.score > 1.0 for e in IDX.entries)


def test_do_not_intervene_customers_are_always_monitor_tier():
    for e in IDX.entries:
        assert (e.tier == TIER_MONITOR) == (e.customer.decision != INTERVENE)


def test_score_matches_the_documented_formula():
    e = IDX.entries[0]
    c = e.components
    expected = 100 * (CFG.weight_value_at_risk * c.value_at_risk_percentile
                      + CFG.weight_churn_probability * c.churn_probability_percentile
                      + CFG.weight_expected_net_benefit * c.expected_net_benefit_percentile)
    assert abs(e.score - expected) < 1e-3


def test_higher_value_at_risk_never_lowers_the_score_when_other_inputs_equal():
    a, b = sorted(IDX.entries, key=lambda e: e.customer.value_at_risk)[:: len(IDX.entries) - 1]
    assert a.components.value_at_risk_percentile < b.components.value_at_risk_percentile


def test_ranking_is_deterministic():
    again = PriorityIndex(make_portfolio(80), CFG)
    assert [e.customer.customer_id for e in again.entries] == [e.customer.customer_id for e in IDX.entries]


def test_pagination_and_filters():
    page = IDX.query(page=1, page_size=10)
    assert len(page.items) == 10 and page.total == 80 and page.page_count == 8
    last = IDX.query(page=999, page_size=10)
    assert last.page == 8
    high = IDX.query(PriorityFilter(risk_band="HIGH"), page_size=200)
    assert high.items and all(e.customer.risk_band == "HIGH" for e in high.items)
    seg = IDX.query(PriorityFilter(segment_id=1), page_size=200)
    assert all(e.customer.segment_id == 1 for e in seg.items)
    one = IDX.query(PriorityFilter(search="t-0005"), page_size=200)
    assert [e.customer.customer_id for e in one.items] == ["T-0005"]
    none = IDX.query(PriorityFilter(search="zzz"))
    assert none.total == 0 and none.items == () and none.page_count == 1


def test_sorting_by_value_at_risk_descending():
    page = IDX.query(sort_by="value_at_risk", descending=True, page_size=200)
    values = [e.customer.value_at_risk for e in page.items]
    assert values == sorted(values, reverse=True)


@pytest.mark.parametrize("kwargs", [
    {"sort_by": "bogus"}, {"page": 0}, {"page_size": 0}, {"page_size": 201},
])
def test_invalid_query_parameters(kwargs):
    with pytest.raises(RetentionInputError):
        IDX.query(**kwargs)


def test_invalid_filters():
    with pytest.raises(RetentionInputError):
        IDX.query(PriorityFilter(tier="P9"))
    with pytest.raises(RetentionInputError):
        IDX.query(PriorityFilter(min_churn_probability=1.5))


def test_reasons_use_only_computed_values_and_make_no_causal_claims():
    for e in IDX.entries[:5] + IDX.entries[-5:]:
        text = " ".join(explain_priority(e, PF))
        assert e.customer.risk_band in text and e.customer.segment_name in text
        assert "cause" not in text.lower() or "not" in text.lower()


def test_empty_portfolio_is_supported():
    from dataclasses import replace

    empty = replace(PF, customers=(), index={})
    index = PriorityIndex(empty, CFG)
    assert index.entries == () and index.query().total == 0
