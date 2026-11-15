"""Phase 13: NPS and CSAT formulas, scale handling, missing responses and survey periods."""

from __future__ import annotations

import pytest

from trichurn_experience.config import parse_config
from trichurn_experience.schemas import BlockedByMissingData
from trichurn_experience.surveys import InvalidSurveyPeriod, compute_csat, compute_nps, parse_period

CFG = parse_config({"surveys": {"min_responses": 5}})
S = CFG.surveys


def rows(scores, date="2026-10-01"):
    return [
        {"response_id": f"r{i}", "customer_id": "C1", "score": s, "survey_date": date} for i, s in enumerate(scores)
    ]


def test_nps_formula_balanced_example():
    # promoters 10,9,9 (3) | passives 8,7 (2) | detractors 6,0,3 (3): 37.5% - 37.5% = 0
    res = compute_nps(rows([10, 9, 9, 8, 7, 6, 0, 3]), S.nps, S)
    assert (res["promoters"], res["passives"], res["detractors"]) == (3, 2, 3)
    assert res["value"] == 0.0 and res["promoters_pct"] == 37.5 and res["detractors_pct"] == 37.5


def test_nps_extremes():
    assert compute_nps(rows([10] * 4), S.nps, S)["value"] == 100.0
    assert compute_nps(rows([0, 3, 6]), S.nps, S)["value"] == -100.0
    assert compute_nps(rows([7, 8]), S.nps, S)["value"] == 0.0


def test_nps_threshold_edges_6_is_detractor_7_8_passive_9_promoter():
    res = compute_nps(rows([6, 7, 8, 9]), S.nps, S)
    assert (res["detractors"], res["passives"], res["promoters"]) == (1, 2, 1)
    assert res["value"] == 0.0


def test_nps_rounding():
    res = compute_nps(rows([10, 9, 8]), S.nps, S)  # 2/3 promoters -> 66.67
    assert res["value"] == 66.67


def test_csat_formula_and_threshold():
    res = compute_csat(rows([5, 4, 3, 2, 1, 5]), S.csat, S)
    assert res["satisfied"] == 3 and res["not_satisfied"] == 3 and res["value"] == 50.0
    assert res["scale"]["satisfied_min"] == 4


def test_csat_custom_scale():
    cfg = parse_config({"surveys": {"csat": {"scale_min": 1, "scale_max": 7, "satisfied_min": 6}}})
    res = compute_csat(rows([7, 6, 5, 1]), cfg.surveys.csat, cfg.surveys)
    assert res["satisfied"] == 2 and res["value"] == 50.0
    with pytest.raises(BlockedByMissingData):
        compute_csat(rows([8]), cfg.surveys.csat, cfg.surveys)  # outside the custom scale


def test_missing_out_of_scale_and_non_numeric_responses_are_counted_not_used():
    data = rows([10, None, "", "abc", 11, -1, True, 9])
    res = compute_nps(data, S.nps, S)
    assert res["responses_total"] == 8 and res["valid_responses"] == 2
    assert res["missing_score"] == 2 and res["out_of_scale"] == 4
    assert res["value"] == 100.0


@pytest.mark.parametrize("fn,scale_attr", [(compute_nps, "nps"), (compute_csat, "csat")])
def test_no_valid_responses_is_blocked_never_zero(fn, scale_attr):
    for empty in ([], rows([None, "", "abc"])):
        with pytest.raises(BlockedByMissingData):
            fn(empty, getattr(S, scale_attr), S)


def test_low_sample_flag_uses_configured_minimum():
    assert compute_nps(rows([10, 9, 3, 8]), S.nps, S)["low_sample"] is True
    assert compute_nps(rows([10, 9, 3, 8, 7]), S.nps, S)["low_sample"] is False


def test_period_filters_by_survey_date_inclusive():
    data = rows([10], "2026-09-30") + rows([0], "2026-10-01") + rows([0], "2026-10-31") + rows([10], "2026-11-01")
    period = parse_period("2026-10-01", "2026-10-31")
    res = compute_nps(data, S.nps, S, period)
    assert res["valid_responses"] == 2 and res["out_of_period"] == 2 and res["value"] == -100.0
    assert res["period"]["start"].startswith("2026-10-01") and res["period"]["end"].startswith("2026-10-31T23:59:59")


def test_period_open_ended_and_none():
    assert parse_period(None, None).start is None
    p = parse_period("2026-10-01", None)
    assert p.end is None and p.contains(parse_period("2030-01-01", None).start)


@pytest.mark.parametrize("start,end", [("2026-11-01", "2026-10-01"), ("garbage", None), (None, "2026-13-01")])
def test_invalid_periods_are_rejected(start, end):
    with pytest.raises(InvalidSurveyPeriod):
        parse_period(start, end)


def test_responses_with_unparseable_dates_are_excluded_when_a_period_is_set():
    data = [{"score": 10, "survey_date": "bad"}, {"score": 9, "survey_date": "2026-10-05"}]
    res = compute_nps(data, S.nps, S, parse_period("2026-10-01", "2026-10-31"))
    assert res["valid_responses"] == 1 and res["out_of_period"] == 1


def test_formula_text_is_documented_in_the_result():
    assert "promoters" in compute_nps(rows([10]), S.nps, S)["formula"]
    assert "satisfied" in compute_csat(rows([5]), S.csat, S)["formula"]
