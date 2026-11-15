"""Phase 4: what-if simulation (assumptions only, non-mutating) and architectural guarantees of ml/business."""
import ast
import copy
from pathlib import Path

import pytest

from ml.business import (
    DO_NOT_INTERVENE,
    INTERVENE,
    Scenario,
    load_business_config,
    simulate,
    sweep_churn_probability,
    sweep_multiplier,
)
from ml.business.schemas import NON_CAUSAL_NOTE, SIMULATION_LABEL
from ml.errors import BusinessInputError

THRESHOLD = 0.34
CLV, P = 3000.0, 0.6
BIZ = Path("ml/business")


@pytest.fixture()
def cfg():
    return load_business_config()


def sim(cfg, base_p=P, base_clv=CLV, **scenario):
    """Baseline (base_p, base_clv) vs a Scenario built from the remaining keyword overrides."""
    return simulate(cfg, base_p, base_clv, Scenario(**scenario), THRESHOLD)


# ------------------------------------------------------------------------------------------ what-if effects
def test_unchanged_scenario_has_zero_delta_and_is_labelled_simulation(cfg):
    r = sim(cfg)
    assert r.label == SIMULATION_LABEL == "SIMULATION / WHAT-IF" and r.note == NON_CAUSAL_NOTE
    assert "does not establish causal" in r.note
    assert r.delta["expected_net_benefit"] == 0 and not r.delta["decision_changed"] and r.assumptions_changed == {}
    assert r.baseline.to_dict() == r.scenario.to_dict()


def test_changing_success_rate_changes_enb(cfg):
    best = sim(cfg).baseline.decision.recommended.action.action_id
    base = sim(cfg).baseline.economics.expected_net_benefit
    up = sim(cfg, action_success_rate={best: 0.9})
    assert up.scenario.economics.expected_net_benefit > base and up.delta["expected_net_benefit"] > 0
    assert up.delta["expected_benefit"] > 0 and up.delta["expected_cost"] == 0
    down = sim(cfg, action_success_rate={best: 0.0})
    assert down.scenario.economics.expected_net_benefit < base


def test_changing_cost_changes_enb(cfg):
    best = sim(cfg).baseline.decision.recommended.action.action_id
    r = sim(cfg, action_cost={best: cfg.actions[best].cost + 50})
    assert r.scenario.economics.expected_net_benefit < r.baseline.economics.expected_net_benefit
    only = load_business_config({"actions": {a: {"enabled": False} for a in cfg.actions if a not in
                                             ("no_action", "retention_email")}})
    r2 = simulate(only, P, CLV, Scenario(action_cost={"retention_email": 100.0}), THRESHOLD)
    rise = 100.0 - only.actions["retention_email"].cost
    assert r2.delta["expected_net_benefit"] == pytest.approx(-rise)       # shown even though the action is now a loss
    assert r2.delta["expected_cost"] == pytest.approx(rise)
    assert r2.scenario.economics.expected_net_benefit < 0 and r2.scenario.decision.decision == DO_NOT_INTERVENE
    assert r2.scenario.economics_action_id == "retention_email"


def test_changing_churn_probability_changes_enb_and_risk_band(cfg):
    r = sim(cfg, churn_probability=0.9)
    assert r.scenario.economics.expected_net_benefit > r.baseline.economics.expected_net_benefit
    assert r.scenario.risk_band == "CRITICAL" and r.baseline.risk_band == "HIGH"
    assert r.baseline.churn_probability == P and r.scenario.churn_probability == 0.9


def test_changing_clv_changes_enb(cfg):
    r = sim(cfg, clv=CLV * 2)
    assert r.scenario.economics.value_at_risk == pytest.approx(2 * r.baseline.economics.value_at_risk)
    assert r.scenario.economics.expected_net_benefit > r.baseline.economics.expected_net_benefit


def test_changing_policy_thresholds_changes_the_decision(cfg):
    assert sim(cfg).baseline.decision.decision == INTERVENE
    blocked = sim(cfg, min_churn_probability=0.9)
    assert blocked.scenario.decision.decision == DO_NOT_INTERVENE and blocked.delta["decision_changed"]
    assert blocked.scenario.economics.expected_net_benefit == blocked.baseline.economics.expected_net_benefit
    assert sim(cfg, min_customer_value=10_000).scenario.decision.decision == DO_NOT_INTERVENE
    assert sim(cfg, min_expected_net_benefit=1e9).scenario.decision.decision == DO_NOT_INTERVENE
    assert sim(cfg, base_p=0.1, min_churn_probability=0.05).scenario.decision.decision in (INTERVENE, DO_NOT_INTERVENE)


def test_recommended_action_can_change_under_new_assumptions(cfg):
    best = sim(cfg).baseline.decision.recommended.action.action_id
    r = sim(cfg, action_success_rate={best: 0.0})
    assert r.delta["recommended_action_changed"] and r.scenario.decision.recommended.action.action_id != best


def test_what_if_does_not_mutate_production_configuration(cfg):
    before = copy.deepcopy(cfg)
    actions_before = dict(cfg.actions)
    sim(cfg, action_cost={"discount_offer": 1.0}, action_success_rate={"discount_offer": 1.0},
        min_churn_probability=0.99, clv=1.0, churn_probability=0.99)
    sweep_churn_probability(cfg, CLV, THRESHOLD)
    sweep_multiplier(cfg, P, CLV, "success_rate", THRESHOLD)
    sweep_multiplier(cfg, P, CLV, "cost", THRESHOLD)
    assert cfg == before and cfg.actions == actions_before and cfg.actions["discount_offer"].cost == 60
    assert load_business_config() == before                       # the file-based production config is unchanged
    with pytest.raises(AttributeError):
        cfg.policy.min_customer_value = 0                         # frozen: cannot be edited in place


def test_scenario_validation(cfg):
    with pytest.raises(BusinessInputError, match="unknown actions"):
        sim(cfg, action_cost={"free_lunch": 1.0})
    with pytest.raises(BusinessInputError, match="no_action"):
        sim(cfg, action_success_rate={"no_action": 0.5})
    with pytest.raises(BusinessInputError, match="no_action"):
        sim(cfg, action_cost={"no_action": 5.0})
    for bad in ({"churn_probability": 1.2}, {"clv": -1.0}, {"action_cost": {"discount_offer": -1.0}},
                {"action_success_rate": {"discount_offer": 2.0}}, {"min_churn_probability": float("nan")},
                {"min_customer_value": -5.0}):
        with pytest.raises(BusinessInputError):
            sim(cfg, **bad)


def test_what_if_is_deterministic(cfg):
    a = sim(cfg, action_cost={"discount_offer": 90.0}, churn_probability=0.7).to_dict()
    b = sim(load_business_config(), action_cost={"discount_offer": 90.0}, churn_probability=0.7).to_dict()
    assert a == b


# ------------------------------------------------------------------------------------------------ sweeps
def test_probability_sweep_is_monotone_in_enb_and_uses_config_defaults(cfg):
    rows = sweep_churn_probability(cfg, CLV, THRESHOLD)
    ps = [r["churn_probability"] for r in rows]
    assert ps[0] == 0.05 and ps[-1] == 0.95 and ps == sorted(ps) and len(ps) == 19
    enb = [r["expected_net_benefit"] for r in rows]
    assert enb == sorted(enb)
    assert rows[0]["decision"] == DO_NOT_INTERVENE and rows[-1]["decision"] == INTERVENE


def test_multiplier_sweeps_move_enb_in_the_expected_direction(cfg):
    sr = [r["expected_net_benefit"] for r in sweep_multiplier(cfg, P, CLV, "success_rate", THRESHOLD)]
    ct = [r["expected_net_benefit"] for r in sweep_multiplier(cfg, P, CLV, "cost", THRESHOLD)]
    assert sr == sorted(sr) and sr[0] < sr[-1]
    assert ct == sorted(ct, reverse=True) and ct[0] > ct[-1]
    with pytest.raises(BusinessInputError):
        sweep_multiplier(cfg, P, CLV, "magic", THRESHOLD)
    capped = sweep_multiplier(cfg, P, CLV, "success_rate", THRESHOLD, multipliers=(1000.0,))
    assert capped[0]["expected_net_benefit"] < 1e9            # success rates are capped at 1, never exceed it


# ----------------------------------------------------------------------------------------- architecture
FORBIDDEN_IMPORTS = ("fastapi", "starlette", "backend", "api", "db", "sqlalchemy", "psycopg", "asyncpg", "redis",
                     "mlflow", "shap", "sklearn", "joblib", "xgboost", "random", "requests", "uvicorn")


def _imports(path):
    for node in ast.walk(ast.parse(path.read_text(encoding="utf-8"))):
        if isinstance(node, ast.Import):
            yield from (a.name for a in node.names)
        elif isinstance(node, ast.ImportFrom) and node.module and node.level == 0:
            yield node.module


def test_business_layer_has_no_web_db_model_or_randomness_dependencies():
    files = sorted(BIZ.glob("*.py"))
    assert len(files) >= 12
    for f in files:
        for mod in _imports(f):
            root = mod.split(".")[0]
            assert root not in FORBIDDEN_IMPORTS, f"{f.name} imports {mod}"
            assert not mod.startswith(("ml.pipelines", "ml.explainability")), f"{f.name} imports {mod}"


def test_no_randomness_and_no_hardcoded_currency_or_business_constants_in_logic():
    for f in BIZ.glob("*.py"):
        src = f.read_text(encoding="utf-8")
        assert "np.random" not in src and "default_rng" not in src and "import random" not in src, f.name
        if f.name != "formatting.py":
            assert "\u20b9" not in src and '"INR"' not in src and "'INR'" not in src, f.name
    for name in ("clv.py", "enb.py", "retention.py", "decision.py", "what_if.py", "risk_bands.py"):
        src = (BIZ / name).read_text(encoding="utf-8")
        for contract in ("Month-to-month", "One year", "Two year", "discount_offer", "retention_email", "CRITICAL"):
            assert contract not in src, f"{name} hard-codes {contract!r}"


def test_explanation_literals_stay_in_sync_with_phase3_schemas():
    from ml.business.explanation import DECREASES, INCREASES
    from ml.explainability.schemas import DECREASES_CHURN, INCREASES_CHURN
    assert (INCREASES, DECREASES) == (INCREASES_CHURN, DECREASES_CHURN)
