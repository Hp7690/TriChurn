from __future__ import annotations

import sqlite3
from datetime import UTC, datetime

import pytest

from retention.campaign_store import CampaignStore, NewAssignment, NewOutcome
from retention.errors import RetentionInputError, RetentionNotFoundError

NOW = datetime(2025, 3, 1, 12, 0, tzinfo=UTC)


def _store(tmp_path=None):
    return CampaignStore(":memory:" if tmp_path is None else tmp_path / "nested" / "c.sqlite3")


def _campaign(store, **kw):
    args = {"name": "Spring offer", "action_id": "discount_offer", "campaign_date": "2025-03-01", "randomized": False}
    args.update(kw)
    return store.create_campaign(args.pop("name"), args.pop("action_id"), args.pop("campaign_date"),
                                 args.pop("randomized"), args.pop("notes", None), now=NOW)


def test_database_starts_completely_empty():
    store = _store()
    assert store.counts() == {"campaigns": 0, "assignments": 0, "outcomes": 0}
    assert store.list_campaigns() == [] and store.assignments() == []


def test_file_database_is_created_empty_with_parent_folders(tmp_path):
    store = _store(tmp_path)
    assert not (tmp_path / "nested").exists()               # nothing happens until first use
    assert store.counts() == {"campaigns": 0, "assignments": 0, "outcomes": 0}
    assert (tmp_path / "nested" / "c.sqlite3").is_file()


def test_data_persists_across_store_instances(tmp_path):
    first = _store(tmp_path)
    c = _campaign(first)
    second = _store(tmp_path)
    assert [x.campaign_id for x in second.list_campaigns()] == [c.campaign_id]


def test_create_and_get_campaign():
    store = _store()
    c = _campaign(store, randomized=True, notes="  hello ")
    got = store.get_campaign(c.campaign_id)
    assert got == c and got.randomized is True and got.notes == "hello"
    with pytest.raises(RetentionNotFoundError):
        store.get_campaign("cmp_missing")


@pytest.mark.parametrize("kwargs", [
    {"name": "  "}, {"name": "x" * 501}, {"campaign_date": "2025-13-40"}, {"campaign_date": "yesterday"},
    {"campaign_date": "1999-01-01"}, {"campaign_date": "2025-W09-6"}, {"notes": "bad\x00note"},
    {"name": "tab\tname"},
])
def test_invalid_campaign_input(kwargs):
    with pytest.raises(RetentionInputError):
        _campaign(_store(), **kwargs)


def test_assign_reports_duplicates_and_keeps_estimates_snapshot():
    store = _store()
    c = _campaign(store)
    items = [NewAssignment("A-1", 60.0, 120.5, 0.7), NewAssignment("A-2", 60.0, 80.0, 0.5)]
    assert store.assign(c.campaign_id, items, now=NOW) == (2, [])
    assert store.assign(c.campaign_id, [NewAssignment("A-1", 1.0, 1.0, 0.1), NewAssignment("A-3", 60.0, 5.0, 0.2)],
                        now=NOW) == (1, ["A-1"])
    rows = {r.customer_id: r for r in store.assignments(c.campaign_id)}
    assert rows["A-1"].estimated_cost == 60.0 and rows["A-1"].estimated_benefit == 120.5     # not overwritten
    assert all(r.outcome is None and r.actual_cost is None for r in rows.values())             # no fabricated actuals


@pytest.mark.parametrize("item", [
    NewAssignment("A-1", 1.0, -1.0, 0.5),
    NewAssignment("A-1", 1.0, float("nan"), 0.5),
    NewAssignment("A-1", 1.0, 1.0, -0.1),
    NewAssignment("A-1", 1.0, 1.0, 1.1),
    NewAssignment("A-1", 1.0, 1.0, float("inf")),
])
def test_invalid_assignment_estimates_are_rejected(item):
    store = _store()
    c = _campaign(store)
    with pytest.raises(RetentionInputError):
        store.assign(c.campaign_id, [item])
    assert store.counts()["assignments"] == 0


def test_assign_to_unknown_campaign_and_bad_group():
    store = _store()
    with pytest.raises(RetentionNotFoundError):
        store.assign("cmp_nope", [NewAssignment("A-1", 1.0, 1.0, 0.1)])
    c = _campaign(store)
    with pytest.raises(RetentionInputError):
        store.assign(c.campaign_id, [NewAssignment("A-1", 1.0, 1.0, 0.1, group="vip")])


def test_outcomes_recorded_once_per_assignment():
    store = _store()
    c = _campaign(store)
    store.assign(c.campaign_id, [NewAssignment("A-1", 60.0, 100.0, 0.6), NewAssignment("A-2", 60.0, 90.0, 0.5)])
    out = store.record_outcomes(c.campaign_id, [
        NewOutcome("A-1", "retained", actual_cost=55.0, actual_retained_revenue=900.0),
        NewOutcome("A-2", "churned"), NewOutcome("A-9", "retained")], now=NOW)
    assert out == (2, ["A-9"], [])
    again = store.record_outcomes(c.campaign_id, [NewOutcome("A-1", "churned")], now=NOW)
    assert again == (0, [], ["A-1"])
    rows = {r.customer_id: r for r in store.assignments(c.campaign_id)}
    assert rows["A-1"].outcome == "retained" and rows["A-1"].actual_retained_revenue == 900.0
    assert rows["A-2"].actual_cost is None


@pytest.mark.parametrize("outcome", [
    NewOutcome("A-1", "won"), NewOutcome("A-1", "retained", actual_cost=-1.0),
    NewOutcome("A-1", "retained", actual_retained_revenue=float("nan")),
    NewOutcome("A-1", "churned", actual_retained_revenue=10.0),
])
def test_invalid_outcomes(outcome):
    store = _store()
    c = _campaign(store)
    store.assign(c.campaign_id, [NewAssignment("A-1", 1.0, 1.0, 0.1)])
    with pytest.raises(RetentionInputError):
        store.record_outcomes(c.campaign_id, [outcome])
    assert store.counts()["outcomes"] == 0


def test_outcome_for_unknown_campaign():
    with pytest.raises(RetentionNotFoundError):
        _store().record_outcomes("cmp_nope", [NewOutcome("A-1", "retained")])


def test_sql_injection_text_is_stored_as_data_not_executed():
    store = _store()
    c = _campaign(store, name="x'); DROP TABLE campaigns;--")
    assert store.get_campaign(c.campaign_id).name == "x'); DROP TABLE campaigns;--"
    store.assign(c.campaign_id, [NewAssignment("A'; DELETE FROM assignments;--", 1.0, 1.0, 0.1)])
    assert store.counts()["campaigns"] == 1 and store.counts()["assignments"] == 1


def test_schema_enforces_outcome_values_even_for_raw_inserts():
    store = _store()
    c = _campaign(store)
    store.assign(c.campaign_id, [NewAssignment("A-1", 1.0, 1.0, 0.1)])
    with store._connect() as conn:                              # noqa: SLF001 - verifying the DB-level constraint
        with pytest.raises(sqlite3.IntegrityError):
            conn.execute("INSERT INTO outcomes VALUES (1, 'bogus', NULL, NULL, 'x')")
