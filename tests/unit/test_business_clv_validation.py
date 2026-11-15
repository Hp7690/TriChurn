"""Phase 4: CLV methodology, numerical safety of every business input, and configuration validation."""
import math

import numpy as np
import pandas as pd
import pytest

from ml.business import (
    compute_clv,
    compute_clv_for_record,
    compute_enb,
    discounted_months,
    load_business_config,
    value_at_risk,
)
from ml.business.config import parse_business_config
from ml.business.validation import require_non_negative, require_probability
from ml.config import load_config
from ml.errors import BusinessConfigError, BusinessInputError, TriChurnError

BAD_NUMBERS = [float("nan"), float("inf"), float("-inf"), None, "0.5", True, [0.5], object()]


@pytest.fixture(scope="module")
def cfg():
    return load_business_config()


def with_clv(**kw):
    return load_business_config({"clv": kw}).clv


# ------------------------------------------------------------------------------------------------------ CLV
def test_clv_normal_calculation_is_revenue_times_assumed_lifetime(cfg):
    r = compute_clv(100.0, "Month-to-month", cfg.clv)
    assert r.clv == pytest.approx(100.0 * cfg.clv.lifetime_months_by_segment["Month-to-month"])
    assert r.lifetime_source == "segment:Month-to-month" and r.discounted_months == r.lifetime_months
    two = compute_clv(100.0, "Two year", cfg.clv)
    assert two.clv == pytest.approx(100.0 * cfg.clv.lifetime_months_by_segment["Two year"]) and two.clv > r.clv


def test_clv_zero_revenue_is_zero(cfg):
    assert compute_clv(0, "One year", cfg.clv).clv == 0.0
    assert compute_clv(0.0, None, cfg.clv).clv == 0.0


def test_clv_boundary_values(cfg):
    assert compute_clv(1e-9, "One year", cfg.clv).clv > 0
    assert math.isfinite(compute_clv(1e12, "Two year", cfg.clv).clv)
    zero_life = with_clv(lifetime_months_by_segment={"Month-to-month": 0})
    assert compute_clv(99, "Month-to-month", zero_life).clv == 0.0


def test_clv_margin_multiplier_and_discounting_follow_the_documented_formula():
    c = with_clv(gross_margin=0.4, revenue_multiplier=2.0, monthly_discount_rate=0.01,
                 lifetime_months_by_segment={"A": 6})
    explicit = sum(1 / 1.01 ** t for t in range(1, 7))
    assert discounted_months(6, 0.01) == pytest.approx(explicit)
    assert compute_clv(10, "A", c).clv == pytest.approx(2.0 * 0.4 * 10 * explicit)
    assert compute_clv(10, "A", c).clv < 2.0 * 0.4 * 10 * 6        # discounting reduces value


def test_clv_missing_segment_uses_documented_default_and_says_so(cfg):
    for seg in (None, float("nan"), "", "  ", "Unlisted Contract"):
        r = compute_clv(50, seg, cfg.clv)
        assert r.lifetime_source == "default" and r.lifetime_months == cfg.clv.default_lifetime_months
    assert compute_clv(50, " One year ", cfg.clv).lifetime_source == "segment:One year"   # whitespace tolerated


def test_clv_missing_segment_raises_when_default_is_disallowed():
    strict = with_clv(allow_default_lifetime=False)
    with pytest.raises(BusinessInputError, match="No configured lifetime"):
        compute_clv(50, "Unlisted", strict)
    with pytest.raises(BusinessInputError):
        compute_clv(50, None, strict)


@pytest.mark.parametrize("missing", [None, float("nan"), "", "   "])
def test_clv_missing_revenue_is_never_invented(cfg, missing):
    with pytest.raises(BusinessInputError, match="missing"):
        compute_clv(missing, "One year", cfg.clv)
    with pytest.raises(BusinessInputError, match="missing"):
        compute_clv_for_record({"MonthlyCharges": missing, "Contract": "One year"}, cfg.clv)


def test_clv_record_without_revenue_column_fails_clearly(cfg):
    with pytest.raises(BusinessInputError, match="no 'MonthlyCharges' column"):
        compute_clv_for_record({"Contract": "One year"}, cfg.clv)


@pytest.mark.parametrize("bad", [-1.0, -0.01, float("nan"), float("inf"), "abc", True])
def test_clv_invalid_revenue_rejected(cfg, bad):
    with pytest.raises((BusinessInputError,)):
        compute_clv(bad, "One year", cfg.clv)


def test_clv_reads_numpy_and_pandas_values(cfg):
    row = pd.Series({"MonthlyCharges": np.float64(70.5), "Contract": "One year"})
    assert compute_clv_for_record(row, cfg.clv).clv == pytest.approx(70.5 * 24)


def test_clv_revenue_field_matches_the_dataset_spec_value_column(cfg, spec):
    assert cfg.clv.revenue_field == spec.value_column      # the CLV input is the column Phase 1 declared as value


# ------------------------------------------------------------------------------------- numerical validation
@pytest.mark.parametrize("bad", BAD_NUMBERS + [-0.1, 1.0000001])
def test_invalid_probability_rejected_everywhere(bad):
    with pytest.raises(BusinessInputError):
        require_probability(bad)
    with pytest.raises(BusinessInputError):
        value_at_risk(100, bad)
    with pytest.raises(BusinessInputError):
        compute_enb(100, bad, 0.2, 10)


@pytest.mark.parametrize("bad", BAD_NUMBERS + [-0.1, 1.5])
def test_invalid_success_rate_rejected(bad):
    with pytest.raises(BusinessInputError, match="action_success_rate"):
        compute_enb(100, 0.5, bad, 10)


@pytest.mark.parametrize("bad", BAD_NUMBERS + [-0.01, -100])
def test_negative_or_invalid_cost_rejected(bad):
    with pytest.raises(BusinessInputError, match="action_cost"):
        compute_enb(100, 0.5, 0.2, bad)


@pytest.mark.parametrize("bad", BAD_NUMBERS + [-0.01, -5000])
def test_invalid_clv_rejected(bad):
    with pytest.raises(BusinessInputError, match="clv"):
        value_at_risk(bad, 0.5)
    with pytest.raises(BusinessInputError, match="clv"):
        compute_enb(bad, 0.5, 0.2, 10)


def test_valid_boundaries_are_accepted():
    assert require_probability(0) == 0.0 and require_probability(1) == 1.0
    assert require_non_negative(0, "x") == 0.0
    assert require_probability(np.float32(0.25)) == pytest.approx(0.25) and isinstance(require_probability(1), float)


def test_errors_are_domain_errors():
    assert issubclass(BusinessInputError, TriChurnError) and issubclass(BusinessConfigError, TriChurnError)


# ------------------------------------------------------------------------------------ config validation
def raw():
    return load_config("business"), load_config("risk_bands")


def test_default_config_loads_and_matches_spec_requirements(cfg):
    assert cfg.currency.code == "INR"
    assert {"no_action", "retention_email", "discount_offer", "loyalty_offer", "priority_support",
            "personalized_offer"} <= set(cfg.actions)
    for a in cfg.actions.values():
        assert a.action_id and a.name and a.cost >= 0 and 0 <= a.success_rate <= 1 and isinstance(a.enabled, bool)
    assert cfg.actions["no_action"].cost == 0 and cfg.actions["no_action"].success_rate == 0
    assert [b.name for b in cfg.risk_bands] == ["LOW", "MEDIUM", "HIGH", "CRITICAL"]


@pytest.mark.parametrize("mutate, message", [
    (lambda b, r: b["actions"]["discount_offer"].update(cost=-1), "cost"),
    (lambda b, r: b["actions"]["discount_offer"].update(success_rate=1.2), "success_rate"),
    (lambda b, r: b["actions"]["discount_offer"].update(success_rate=float("nan")), "success_rate"),
    (lambda b, r: b["actions"].pop("no_action"), "mandatory"),
    (lambda b, r: b["actions"]["no_action"].update(cost=5), "no_action"),
    (lambda b, r: b["actions"]["no_action"].update(success_rate=0.1), "no_action"),
    (lambda b, r: b["actions"]["no_action"].update(enabled=False), "no_action"),
    (lambda b, r: b["actions"]["loyalty_offer"].pop("cost"), "missing"),
    (lambda b, r: b["policy"].update(min_churn_probability=1.5), "min_churn_probability"),
    (lambda b, r: b["policy"].update(min_customer_value=-1), "min_customer_value"),
    (lambda b, r: b["clv"].update(method="magic"), "clv.method"),
    (lambda b, r: b["clv"].update(gross_margin=1.5), "gross_margin"),
    (lambda b, r: b["clv"].update(default_lifetime_months=-3), "default_lifetime_months"),
    (lambda b, r: b.pop("currency"), "currency"),
    (lambda b, r: r["bands"].__setitem__(0, {"name": "LOW", "min_probability": 0.1}), "start at"),
    (lambda b, r: r["bands"].__setitem__(2, {"name": "HIGH", "min_probability": 0.1}), "increasing"),
    (lambda b, r: r["bands"].__setitem__(1, {"name": "LOW", "min_probability": 0.3}), "unique"),
    (lambda b, r: r.update(bands=[]), "non-empty"),
    (lambda b, r: b["what_if"]["sweeps"]["churn_probability"].update(step=0), "step"),
])
def test_invalid_configuration_is_rejected_with_a_clear_error(mutate, message):
    b, r = raw()
    mutate(b, r)
    with pytest.raises(BusinessConfigError, match=message):
        parse_business_config(b, r)


def test_config_objects_are_immutable(cfg):
    with pytest.raises(AttributeError):
        cfg.currency.code = "USD"
    with pytest.raises(AttributeError):
        cfg.actions["discount_offer"].cost = 0
