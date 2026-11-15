"""Phase 4: value at risk, expected net benefit, action selection, intervention policy, risk bands, profiles."""
import copy

import numpy as np
import pytest

from ml.business import (
    DO_NOT_INTERVENE,
    INTERVENE,
    BusinessEngine,
    assign_risk_band,
    compute_enb,
    decide,
    evaluate_actions,
    load_business_config,
    resolve_policy,
    select_best_action,
    value_at_risk,
)
from ml.business.explanation import DECREASES, INCREASES
from ml.business.formatting import format_money, format_profile
from ml.errors import BusinessInputError

THRESHOLD = 0.34


@pytest.fixture(scope="module")
def cfg():
    return load_business_config()


def cfg_with(**sections):
    return load_business_config(sections)


def run(cfg, clv, p, threshold=THRESHOLD):
    return decide(clv, p, cfg.actions, resolve_policy(cfg.policy, threshold))


# ---------------------------------------------------------------------------------------------- value at risk
def test_value_at_risk_at_probability_zero_and_one_and_in_between():
    assert value_at_risk(1000, 0) == 0.0
    assert value_at_risk(1000, 1) == 1000.0
    assert value_at_risk(1000, 0.25) == pytest.approx(250.0)
    assert value_at_risk(0, 0.9) == 0.0


# ----------------------------------------------------------------------------------------------------- ENB
def test_enb_components_and_formula_positive_case():
    b = compute_enb(clv=48000, churn_probability=0.78, action_success_rate=0.25, action_cost=1500)
    assert b.value_at_risk == pytest.approx(37440.0)
    assert b.expected_benefit == pytest.approx(9360.0)
    assert b.expected_cost == 1500 and b.action_cost == 1500
    assert b.expected_net_benefit == pytest.approx(7860.0)
    assert b.expected_net_benefit == pytest.approx(48000 * 0.78 * 0.25 - 1500)        # the documented formula
    assert (b.clv, b.churn_probability, b.action_success_rate) == (48000, 0.78, 0.25)


def test_enb_zero_negative_and_zero_cost():
    assert compute_enb(1000, 0.5, 0.2, 100).expected_net_benefit == pytest.approx(0.0)       # break-even
    assert compute_enb(1000, 0.5, 0.1, 100).expected_net_benefit == pytest.approx(-50.0)     # not worthwhile
    free = compute_enb(1000, 0.5, 0.1, 0)
    assert free.expected_net_benefit == free.expected_benefit == pytest.approx(50.0)
    assert compute_enb(1000, 0.5, 0.0, 0).expected_net_benefit == 0.0                         # no_action-like


def test_enb_with_zero_probability_or_value_equals_minus_cost():
    assert compute_enb(1000, 0.0, 0.5, 30).expected_net_benefit == -30.0
    assert compute_enb(0, 0.9, 0.5, 30).expected_net_benefit == -30.0


# ------------------------------------------------------------------------------------------ invariants
GRID = np.random.default_rng(0)      # fixed seed: deterministic property-style tests (no hypothesis dependency)
CASES = [(float(c), float(p), float(s), float(k)) for c, p, s, k in zip(
    GRID.uniform(1, 50_000, 200), GRID.uniform(0.01, 0.99, 200), GRID.uniform(0.01, 0.9, 200),
    GRID.uniform(0, 2_000, 200), strict=True)]


@pytest.mark.parametrize("clv,p,s,k", CASES)
def test_invariants_enb_monotonic_in_every_input(clv, p, s, k):
    base = compute_enb(clv, p, s, k).expected_net_benefit
    assert compute_enb(clv, p, min(1.0, s + 0.05), k).expected_net_benefit > base - 1e-12   # success_rate up -> ENB up
    assert compute_enb(clv, p, s, k + 10).expected_net_benefit < base                       # cost up -> ENB down
    assert compute_enb(clv, min(1.0, p + 0.01), s, k).expected_net_benefit >= base           # probability up
    assert compute_enb(clv + 100, p, s, k).expected_net_benefit > base                       # CLV up
    assert value_at_risk(clv, min(1.0, p + 0.01)) >= value_at_risk(clv, p)
    assert value_at_risk(clv + 100, p) > value_at_risk(clv, p)
    b = compute_enb(clv, p, s, k)                                                            # identities
    assert b.expected_net_benefit == pytest.approx(b.expected_benefit - b.expected_cost)
    assert b.value_at_risk == pytest.approx(clv * p) and b.expected_benefit == pytest.approx(clv * p * s)


# ------------------------------------------------------------------------------------- action selection
def test_best_action_is_the_highest_enb_eligible_action(cfg):
    ev = evaluate_actions(cfg.actions, 3000, 0.8)
    best = select_best_action(ev, 0)
    expected = max((e for e in ev if e.action.action_id != "no_action" and e.eligible),
                   key=lambda e: e.enb.expected_net_benefit)
    assert best is expected and best.enb.expected_net_benefit > 0
    assert all(best.enb.expected_net_benefit >= e.enb.expected_net_benefit for e in ev if e.eligible)


def test_negative_enb_actions_are_never_recommended(cfg):
    ev = evaluate_actions(cfg.actions, 600, 0.36)         # low value at risk: only cheap actions pay off
    best = select_best_action(ev, 0)
    assert best is None or best.enb.expected_net_benefit > 0
    r = run(cfg, 600, 0.36)
    assert r.recommended.enb.expected_net_benefit >= 0
    expensive = next(e for e in ev if e.action.action_id == "personalized_offer")
    assert expensive.enb.expected_net_benefit < 0 and r.recommended.action.action_id != "personalized_offer"


def test_disabled_actions_are_ignored(cfg):
    best_id = run(cfg, 3000, 0.8).recommended.action.action_id
    off = cfg_with(actions={best_id: {"enabled": False}})
    r = run(off, 3000, 0.8)
    assert best_id not in {e.action.action_id for e in r.evaluations}
    assert r.recommended.action.action_id != best_id and r.decision == INTERVENE


def test_no_profitable_action_means_no_action(cfg):
    only_costly = cfg_with(actions={a: {"cost": 1e9} for a in cfg.actions if a != "no_action"})
    r2 = run(only_costly, 5000, 0.9)
    assert r2.decision == DO_NOT_INTERVENE and r2.recommended.action.action_id == "no_action"
    assert r2.recommended.enb.expected_net_benefit == 0 and r2.best_eligible is None
    assert r2.reasons[0].code == "NO_ACTION_WITH_ENB_ABOVE_MINIMUM"


def test_only_no_action_enabled_is_valid():
    cfg = cfg_with(actions={a: {"enabled": False} for a in
                            ("retention_email", "loyalty_offer", "priority_support", "discount_offer",
                             "personalized_offer")})
    r = run(cfg, 5000, 0.9)
    assert r.decision == DO_NOT_INTERVENE and [e.action.action_id for e in r.evaluations] == ["no_action"]


def test_min_clv_eligibility_and_cost_cap_are_respected(cfg):
    ev = {e.action.action_id: e for e in evaluate_actions(cfg.actions, 800, 0.9)}
    assert not ev["priority_support"].eligible and "minimum" in ev["priority_support"].ineligible_reason
    assert not ev["personalized_offer"].eligible
    capped = cfg_with(policy={"max_action_cost": 30})
    r = run(capped, 5000, 0.9)
    assert r.recommended.action.cost <= 30 and r.recommended.action.action_id == "loyalty_offer"
    cev = {e.action.action_id: e for e in r.evaluations}
    assert not cev["discount_offer"].eligible and "cap" in cev["discount_offer"].ineligible_reason
    assert cev["no_action"].eligible


ONLY = ("retention_email", "loyalty_offer", "priority_support", "discount_offer", "personalized_offer")


def only_enabled(**actions):
    """Config where just the named actions (plus no_action) are enabled, with the given overrides."""
    base = {a: {"enabled": False} for a in ONLY}
    for a, o in actions.items():
        base[a] = {"enabled": True, **o}
    return cfg_with(actions=base, policy={"min_customer_value": 0})


def test_ties_break_by_lower_cost_then_action_id():
    # clv*p = 1024 exactly, so both actions have ENB exactly 200 (binary-exact numbers)
    tie = only_enabled(loyalty_offer={"cost": 56, "success_rate": 0.25},
                       discount_offer={"cost": 184, "success_rate": 0.375})
    ev = {e.action.action_id: e.enb.expected_net_benefit for e in evaluate_actions(tie.actions, 2048, 0.5)}
    assert ev["loyalty_offer"] == ev["discount_offer"] == 200.0
    assert run(tie, 2048, 0.5).recommended.action.action_id == "loyalty_offer"      # cheaper wins
    full = only_enabled(loyalty_offer={"cost": 56, "success_rate": 0.25},
                        discount_offer={"cost": 56, "success_rate": 0.25})
    assert run(full, 2048, 0.5).recommended.action.action_id == "discount_offer"          # full tie -> action_id
    flipped = only_enabled(discount_offer={"cost": 56, "success_rate": 0.25},
                           loyalty_offer={"cost": 56, "success_rate": 0.25})              # config order must not matter
    assert run(flipped, 2048, 0.5).recommended.action.action_id == "discount_offer"


def test_action_must_beat_the_minimum_enb_strictly(cfg):
    ev = evaluate_actions(cfg.actions, 3000, 0.8)
    top = max(e.enb.expected_net_benefit for e in ev)
    assert select_best_action(ev, top) is None                      # equal is not enough
    assert select_best_action(ev, top - 1e-6) is not None


# ----------------------------------------------------------------------------------- intervention policy
def test_positive_enb_and_all_gates_pass_means_intervene_with_reasons(cfg):
    r = run(cfg, 3000, 0.8)
    assert r.decision == INTERVENE and r.recommended is r.best_eligible
    codes = [x.code for x in r.reasons]
    assert codes == ["CHURN_PROBABILITY_AT_OR_ABOVE_MINIMUM", "CUSTOMER_VALUE_AT_OR_ABOVE_MINIMUM",
                     "POSITIVE_EXPECTED_NET_BENEFIT", "ACTION_JUSTIFIED_UNDER_ASSUMPTIONS"]


def test_negative_enb_means_no_intervention(cfg):
    tough = cfg_with(actions={a: {"cost": 5000} for a in cfg.actions if a != "no_action"})
    r = run(tough, 3000, 0.8)
    assert r.decision == DO_NOT_INTERVENE and r.recommended.action.action_id == "no_action"
    assert [x.code for x in r.reasons] == ["NO_ACTION_WITH_ENB_ABOVE_MINIMUM"]


def test_below_churn_threshold_means_no_intervention_even_if_enb_is_positive(cfg):
    r = run(cfg, 50_000, THRESHOLD - 0.01)
    assert r.best_eligible is not None and r.best_eligible.enb.expected_net_benefit > 0     # economics alone pay off
    assert r.decision == DO_NOT_INTERVENE and r.recommended.action.action_id == "no_action"
    assert [x.code for x in r.reasons] == ["CHURN_PROBABILITY_BELOW_MINIMUM"]
    assert run(cfg, 50_000, THRESHOLD).decision == INTERVENE                                   # boundary is inclusive


def test_below_customer_value_means_no_intervention(cfg):
    floor = cfg.policy.min_customer_value
    r = run(cfg, floor - 1, 0.99)
    assert r.decision == DO_NOT_INTERVENE and "CUSTOMER_VALUE_BELOW_MINIMUM" in [x.code for x in r.reasons]
    assert run(cfg_with(policy={"min_expected_net_benefit": -1e9}), floor, 0.99).reasons[1].code == \
        "CUSTOMER_VALUE_AT_OR_ABOVE_MINIMUM"                                                  # boundary is inclusive


def test_multiple_failures_are_all_reported(cfg):
    r = run(cfg, 10, 0.01)
    assert {x.code for x in r.reasons} == {"CHURN_PROBABILITY_BELOW_MINIMUM", "CUSTOMER_VALUE_BELOW_MINIMUM",
                                           "NO_ACTION_WITH_ENB_ABOVE_MINIMUM"}


def test_zero_enb_does_not_trigger_intervention():
    exact = only_enabled(retention_email={"cost": 256, "success_rate": 0.25})      # ENB = 1024*0.25 - 256 = 0 exactly
    r = run(exact, 2048, 0.5)
    assert r.evaluations[1].enb.expected_net_benefit == 0.0
    assert r.best_eligible is None and r.decision == DO_NOT_INTERVENE and r.recommended.action.action_id == "no_action"
    just_positive = only_enabled(retention_email={"cost": 255, "success_rate": 0.25})
    assert run(just_positive, 2048, 0.5).decision == INTERVENE
    too_costly = only_enabled(retention_email={"cost": 257, "success_rate": 0.25})
    assert run(too_costly, 2048, 0.5).decision == DO_NOT_INTERVENE


def test_model_threshold_sentinel_requires_a_threshold_and_numeric_policy_overrides_it(cfg):
    assert cfg.policy.min_churn_probability == "model_threshold"
    assert resolve_policy(cfg.policy, 0.4).min_churn_probability == 0.4
    with pytest.raises(BusinessInputError, match="model_threshold"):
        resolve_policy(cfg.policy, None)
    fixed = cfg_with(policy={"min_churn_probability": 0.6})
    assert resolve_policy(fixed.policy, None).min_churn_probability == 0.6
    assert resolve_policy(fixed.policy, 0.1).min_churn_probability == 0.6


# ------------------------------------------------------------------------------------------- risk bands
def test_risk_bands_boundaries_follow_the_configuration(cfg):
    edges = {b.name: b.min_probability for b in cfg.risk_bands}
    assert assign_risk_band(0.0, cfg.risk_bands) == "LOW" and assign_risk_band(1.0, cfg.risk_bands) == "CRITICAL"
    for b in cfg.risk_bands:
        assert assign_risk_band(b.min_probability, cfg.risk_bands) == b.name        # lower edge inclusive
    assert assign_risk_band(edges["MEDIUM"] - 1e-9, cfg.risk_bands) == "LOW"
    with pytest.raises(BusinessInputError):
        assign_risk_band(1.2, cfg.risk_bands)


def test_risk_band_thresholds_come_from_config_not_code():
    c = load_business_config()
    from ml.config import load_config
    rb = load_config("risk_bands")
    rb["bands"] = [{"name": "OK", "min_probability": 0.0}, {"name": "WATCH", "min_probability": 0.9}]
    from ml.business.config import parse_business_config
    custom = parse_business_config(load_config("business"), rb)
    assert assign_risk_band(0.89, custom.risk_bands) == "OK" and assign_risk_band(0.9, custom.risk_bands) == "WATCH"
    assert assign_risk_band(0.89, c.risk_bands) == "CRITICAL"   # default bands: >= 0.75


# ---------------------------------------------------------------------------------------- business profile
RECORD = {"customerID": "C-1", "MonthlyCharges": 100.0, "Contract": "Two year"}


def test_profile_has_every_required_field_and_consistent_numbers(cfg):
    prof = BusinessEngine(cfg, THRESHOLD).profile(0.8, RECORD, "C-1")
    d = prof.to_dict()
    for k in ("customer_id", "churn_probability", "risk_band", "clv", "value_at_risk", "recommended_action",
              "recommended_action_id", "action_cost", "action_success_rate", "expected_benefit", "expected_cost",
              "expected_net_benefit", "intervention_decision", "decision_reasons"):
        assert k in d
    assert prof.clv == pytest.approx(100 * 36) and prof.value_at_risk == pytest.approx(prof.clv * 0.8)
    assert prof.risk_band == "CRITICAL" and prof.intervention_decision == INTERVENE
    assert prof.expected_net_benefit == pytest.approx(prof.value_at_risk * prof.action_success_rate - prof.action_cost)
    assert prof.expected_net_benefit == pytest.approx(prof.expected_benefit - prof.expected_cost)
    assert len(prof.decision_reason_messages) == len(prof.decision_reasons) == 4
    assert [e["action_id"] for e in d["action_evaluations"]][0] == "no_action"


def test_profile_when_not_intervening_recommends_no_action_but_keeps_value_at_risk(cfg):
    prof = BusinessEngine(cfg, THRESHOLD).profile(0.05, RECORD, "C-2")
    assert prof.intervention_decision == DO_NOT_INTERVENE and prof.recommended_action_id == "no_action"
    assert prof.action_cost == 0 and prof.action_success_rate == 0 and prof.expected_net_benefit == 0
    assert prof.value_at_risk == pytest.approx(prof.clv * 0.05) and prof.risk_band == "LOW"


def test_profile_rejects_bad_inputs(cfg):
    eng = BusinessEngine(cfg, THRESHOLD)
    with pytest.raises(BusinessInputError):
        eng.profile(1.5, RECORD)
    with pytest.raises(BusinessInputError):
        eng.profile(0.5, {"Contract": "Two year"})
    with pytest.raises(BusinessInputError):
        BusinessEngine(cfg, None).profile(0.5, RECORD)             # model_threshold policy needs a threshold
    with pytest.raises(BusinessInputError):
        BusinessEngine(cfg, 1.5)


def test_profile_frame_aligns_probabilities_and_ids(cfg):
    import pandas as pd
    frame = pd.DataFrame([{"customerID": "A", "MonthlyCharges": 90.0, "Contract": "One year"},
                          {"customerID": "B", "MonthlyCharges": 20.0, "Contract": "Month-to-month"}])
    out = BusinessEngine(cfg, THRESHOLD).profile_frame(frame, [0.9, 0.1], "customerID")
    assert [p.customer_id for p in out] == ["A", "B"] and out[0].churn_probability == 0.9
    with pytest.raises(BusinessInputError, match="probabilities"):
        BusinessEngine(cfg, THRESHOLD).profile_frame(frame, [0.9], "customerID")
    with pytest.raises(BusinessInputError, match="id column"):
        BusinessEngine(cfg, THRESHOLD).profile_frame(frame, [0.9, 0.1], "nope")


# ------------------------------------------------------------------------ determinism & presentation
def test_identical_inputs_give_identical_outputs(cfg):
    a = BusinessEngine(cfg, THRESHOLD).profile(0.61, RECORD, "X").to_dict()
    b = BusinessEngine(load_business_config(), THRESHOLD).profile(0.61, copy.deepcopy(RECORD), "X").to_dict()
    assert a == b
    ra, rb = run(cfg, 1234.5, 0.77), run(cfg, 1234.5, 0.77)
    assert ra == rb


def test_currency_is_a_label_only_numbers_do_not_change(cfg):
    usd = cfg_with(currency={"code": "USD", "symbol": "$"})
    a, b = BusinessEngine(cfg, THRESHOLD).profile(0.8, RECORD), BusinessEngine(usd, THRESHOLD).profile(0.8, RECORD)
    da, db = a.to_dict(), b.to_dict()
    assert (da.pop("currency"), db.pop("currency")) == ("INR", "USD")
    assert da.pop("decision_reason_messages") != db.pop("decision_reason_messages")   # text carries the symbol
    assert da == db                                                                    # every number is identical
    assert format_money(1234.5, cfg.currency) == "\u20b91,234.50" and format_money(-5, usd.currency) == "-$5.00"
    assert "\u20b9" in format_profile(a, cfg.currency) and "$" in format_profile(b, usd.currency)


def test_wording_never_claims_an_action_prevents_churn(cfg):
    prof = BusinessEngine(cfg, THRESHOLD).profile(0.8, RECORD, "C-1")
    text = (format_profile(prof, cfg.currency) + BusinessEngine(cfg, THRESHOLD).explain(prof).business_decision).lower()
    for banned in ("will prevent", "prevents churn", "will retain", "will save", "causes"):
        assert banned not in text
    assert "assumption" in text


def test_business_explanation_separates_model_and_decision_sections(cfg):
    from types import SimpleNamespace as NS
    prof = BusinessEngine(cfg, THRESHOLD).profile(0.8, RECORD, "C-1")
    fake = NS(features=[NS(source_feature="Contract", raw_value="Two year", shap_value=0.9, direction=INCREASES),
                        NS(source_feature="tenure", raw_value=2, shap_value=-0.7, direction=DECREASES)])
    ex = BusinessEngine(cfg, THRESHOLD).explain(prof, fake).to_dict()
    assert set(ex) == {"MODEL EXPLANATION", "BUSINESS DECISION", "disclaimer"}
    assert "Contract" in ex["MODEL EXPLANATION"] and "not causes" in ex["MODEL EXPLANATION"]
    assert "higher model score" in ex["MODEL EXPLANATION"] and "lower model score" in ex["MODEL EXPLANATION"]
    assert "Contract" not in ex["BUSINESS DECISION"] and "expected net benefit" in ex["BUSINESS DECISION"]
    assert "does not establish causal" in ex["disclaimer"]
    none = BusinessEngine(cfg, THRESHOLD).explain(prof, None)
    assert "No per-feature explanation" in none.model_explanation
