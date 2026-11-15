"""Phase 13: tenure-based lifecycle proxy (bucketing, aggregation, missing data, risk availability)."""

from __future__ import annotations

import csv
import math
from pathlib import Path

import pytest

from trichurn_experience.config import parse_config
from trichurn_experience.lifecycle import assign_group, compute_lifecycle, read_customer_csv

CFG = parse_config({"lifecycle": {"min_group_size_for_rate": 2}}).lifecycle
GROUPS = CFG.groups
COLS = ["customerID", "tenure", "Contract", "MonthlyCharges", "TotalCharges", "Churn"]


def row(cid, tenure, contract="Month-to-month", monthly="50", total="500", churn="No", **extra):
    return {
        "customerID": cid,
        "tenure": tenure,
        "Contract": contract,
        "MonthlyCharges": monthly,
        "TotalCharges": total,
        "Churn": churn,
        **extra,
    }


@pytest.mark.parametrize(
    "tenure,name",
    [
        (0, "New Customer"),
        (5, "New Customer"),
        (5.99, "New Customer"),
        (6, "Early Lifecycle"),
        (11, "Early Lifecycle"),
        (12, "Developing Customer"),
        (23, "Developing Customer"),
        (24, "Established Customer"),
        (47, "Established Customer"),
        (48, "Long-Term Customer"),
        (72, "Long-Term Customer"),
        (1000, "Long-Term Customer"),
    ],
)
def test_bucket_boundaries_are_min_inclusive_max_exclusive(tenure, name):
    assert assign_group(tenure, GROUPS) == name


@pytest.mark.parametrize("bad", [-1, -0.01, math.nan, math.inf, -math.inf])
def test_invalid_tenure_has_no_group(bad):
    assert assign_group(bad, GROUPS) is None


def test_customer_counts_and_shares_sum_to_analysed():
    rows = [row("a", "1"), row("b", "2"), row("c", "7"), row("d", "13"), row("e", "30"), row("f", "60"), row("g", "72")]
    res = compute_lifecycle(COLS, rows, CFG)
    assert res["customers_total"] == res["customers_analysed"] == 7 and res["status"] == "AVAILABLE"
    assert [g["customers"] for g in res["groups"]] == [2, 1, 1, 1, 2]
    assert sum(g["share_pct"] for g in res["groups"]) == pytest.approx(100, abs=0.05)
    assert res["label"] == "TENURE_PROXY" and res["is_event_based"] is False


def test_churn_distribution_uses_observed_labels_and_withholds_small_groups():
    rows = [
        row("a", "1", churn="Yes"),
        row("b", "2", churn="No"),
        row("c", "3", churn="Yes"),  # New: 3 labelled, 2 churned
        row("d", "7", churn="Yes"),
    ]  # Early: 1 labelled < 2
    res = compute_lifecycle(COLS, rows, CFG)
    new, early = res["groups"][0], res["groups"][1]
    assert new["churn"]["churned"] == 2 and new["churn"]["churn_rate_pct"] == pytest.approx(66.67)
    assert early["churn"]["churn_rate_pct"] is None and "Fewer than 2" in early["churn"]["rate_withheld_reason"]
    assert res["overall"] == {"churn_labels_known": 4, "churned": 3, "churn_rate_pct": 75.0}


def test_unknown_churn_labels_are_not_counted_as_either_class():
    rows = [
        row("a", "1", churn="Yes"),
        row("b", "1", churn=""),
        row("c", "1", churn="maybe"),
        row("d", "1", churn="No"),
    ]
    g = compute_lifecycle(COLS, rows, CFG)["groups"][0]
    assert g["customers"] == 4 and g["churn"]["known_labels"] == 2 and g["churn"]["churned"] == 1


def test_contract_distribution_and_monthly_charge_summary():
    rows = [
        row("a", "1", "Month-to-month", "10"),
        row("b", "2", "One year", "20"),
        row("c", "3", "One year", "40"),
        row("d", "4", "", ""),
    ]
    g = compute_lifecycle(COLS, rows, CFG)["groups"][0]
    assert g["contract_distribution"] == {"Month-to-month": 1, "One year": 2, "Unknown": 1}
    mc = g["monthly_charges"]
    assert (mc["count"], mc["mean"], mc["median"], mc["min"], mc["max"], mc["sum"]) == (
        3,
        23.33,
        20.0,
        10.0,
        40.0,
        70.0,
    )


def test_blank_total_charges_are_counted_missing_not_filled():
    rows = [row("a", "0", total=" "), row("b", "1", total="100"), row("c", "2", total="abc")]
    tc = compute_lifecycle(COLS, rows, CFG)["groups"][0]["total_charges"]
    assert tc["missing"] == 2 and tc["count"] == 1 and tc["mean"] == 100.0


def test_missing_negative_and_non_numeric_tenure_are_excluded_and_counted():
    rows = [row("a", "1"), row("b", ""), row("c", "-3"), row("d", "abc"), row("e", "nan"), row("f", None)]
    res = compute_lifecycle(COLS, rows, CFG)
    assert res["customers_total"] == 6 and res["customers_analysed"] == 1
    assert res["excluded"] == {"total": 5, "invalid_or_missing_tenure": 5}


def test_missing_tenure_column_fails_validation_instead_of_guessing():
    res = compute_lifecycle(["customerID", "Churn"], [{"customerID": "a", "Churn": "No"}], CFG)
    assert res["status"] == "VALIDATION_FAILED" and res["groups"] == [] and res["columns_missing"] == ["tenure"]


def test_no_churn_column_is_partial_and_has_no_churn_figures():
    res = compute_lifecycle(["customerID", "tenure"], [{"customerID": "a", "tenure": "3"}], CFG)
    assert (
        res["status"] == "PARTIALLY_AVAILABLE"
        and res["groups"][0]["churn"] is None
        and res["overall"]["churn_rate_pct"] is None
    )


def test_empty_dataset_is_blocked_not_zero_filled():
    res = compute_lifecycle(COLS, [], CFG)
    assert res["status"] == "BLOCKED_BY_MISSING_DATA" and res["overall"]["churn_rate_pct"] is None
    assert all(g["share_pct"] is None for g in res["groups"])


def test_risk_distribution_is_blocked_without_existing_probabilities():
    res = compute_lifecycle(COLS, [row("a", "1")], CFG)
    assert res["risk_distribution"]["status"] == "BLOCKED_BY_MISSING_DATA" and res["risk_distribution"]["bands"] is None
    assert res["groups"][0]["risk"] is None


def test_risk_distribution_from_dataset_probability_column():
    cols = [*COLS, "churn_probability"]
    rows = [
        row("a", "1", churn_probability="0.05"),
        row("b", "2", churn_probability="0.30"),
        row("c", "3", churn_probability="0.90"),
        row("d", "4", churn_probability="1.5"),
        row("e", "5", churn_probability=""),
    ]
    res = compute_lifecycle(cols, rows, CFG)
    assert res["risk_distribution"]["bands"] == {"LOW": 1, "MEDIUM": 1, "HIGH": 1}
    assert res["risk_distribution"]["missing_probability"] == 2  # out of range and blank are not guessed
    assert res["groups"][0]["risk"]["counts"] == {"LOW": 1, "MEDIUM": 1, "HIGH": 1}


def test_risk_distribution_from_injected_probability_mapping():
    res = compute_lifecycle(COLS, [row("a", "1"), row("b", "2")], CFG, probability_by_customer={"a": 0.1, "b": 0.7})
    assert res["risk_distribution"]["bands"] == {"LOW": 1, "MEDIUM": 0, "HIGH": 1}
    assert "provider" in res["risk_distribution"]["source"]


def test_risk_band_edges_follow_configured_thresholds():
    cols = [*COLS, "churn_probability"]
    rows = [
        row("a", "1", churn_probability="0.2"),
        row("b", "1", churn_probability="0.5"),
        row("c", "1", churn_probability="0"),
    ]
    assert compute_lifecycle(cols, rows, CFG)["risk_distribution"]["bands"] == {"LOW": 1, "MEDIUM": 1, "HIGH": 1}


def test_custom_thresholds_change_the_grouping():
    cfg = parse_config(
        {
            "lifecycle": {
                "groups": [
                    {"name": "Young", "min_months": 0, "max_months": 10},
                    {"name": "Old", "min_months": 10, "max_months": None},
                ]
            }
        }
    ).lifecycle
    res = compute_lifecycle(COLS, [row("a", "9"), row("b", "10")], cfg)
    assert [(g["name"], g["customers"]) for g in res["groups"]] == [("Young", 1), ("Old", 1)]


def test_methodology_assumptions_and_limitations_are_always_present():
    res = compute_lifecycle(COLS, [row("a", "1")], CFG)
    assert "not an event-based customer journey" in res["methodology"]
    assert res["assumptions"] and res["limitations"] and res["thresholds"][0]["name"] == "New Customer"


# --------------------------------------------------------------------- real dataset (skipped if the CSV is absent)
TELCO = Path(__file__).resolve().parents[2] / "ml" / "data" / "raw" / "telco_churn.csv"


@pytest.mark.skipif(not TELCO.is_file(), reason="Telco CSV not present in this checkout")
def test_real_telco_counts_match_an_independent_recount():
    columns, rows = read_customer_csv(TELCO)
    res = compute_lifecycle(columns, rows, parse_config({}).lifecycle)
    with open(TELCO, encoding="utf-8-sig", newline="") as fh:
        raw = list(csv.DictReader(fh))
    assert res["customers_total"] == len(raw) == sum(g["customers"] for g in res["groups"]) + res["excluded"]["total"]
    assert res["overall"]["churned"] == sum(r["Churn"] == "Yes" for r in raw)
    assert res["groups"][0]["total_charges"]["missing"] == sum(1 for r in raw if not r["TotalCharges"].strip())
    for g in res["groups"]:
        lo, hi = g["min_months"], g["max_months"]
        expected = sum(1 for r in raw if int(r["tenure"]) >= lo and (hi is None or int(r["tenure"]) < hi))
        assert g["customers"] == expected
