"""Phase 4 on the real locked Phase 2 artifact and the real Telco CSV.

Customers come from the TRAIN split only (the held-out TEST split is never read). The model is only *used*:
the artifact bytes must be identical afterwards.
"""
import hashlib
import json
import math
from pathlib import Path

import pytest

from ml.business import DO_NOT_INTERVENE, INTERVENE, BusinessEngine, Scenario, load_business_config, simulate
from ml.explainability import ChurnShapExplainer, load_train_background, load_verified_artifact
from ml.pipelines.ingestion import load_csv
from ml.pipelines.training import split_raw

MODEL = Path("models/trichurn_churn_model_v2.0.0.joblib")
META = MODEL.with_name(f"{MODEL.stem}.metadata.json")
CSV = Path("ml/data/raw/telco_churn.csv")
pytestmark = [pytest.mark.integration,
              pytest.mark.skipif(not (MODEL.exists() and CSV.exists()), reason="needs models/ and `make data`")]


def sha(p: Path) -> str:
    return hashlib.sha256(p.read_bytes()).hexdigest()


@pytest.fixture(scope="module")
def world(spec, training_cfg):
    before = (sha(MODEL), sha(META))
    verified = load_verified_artifact(MODEL)
    parts = split_raw(load_csv(CSV), spec, training_cfg["split"]["val_size"], training_cfg["split"]["test_size"],
                      training_cfg["seed"])
    customers = parts.train.head(300)
    probs = verified.artifact.predict_proba(customers)
    cfg = load_business_config()
    engine = BusinessEngine(cfg, verified.artifact.threshold)
    profiles = engine.profile_frame(customers, probs, spec.id_column)
    return {"before": before, "verified": verified, "parts": parts, "customers": customers, "probs": probs,
            "cfg": cfg, "engine": engine, "profiles": profiles}


def test_profiles_are_valid_and_follow_the_policy_independently_recomputed(world):
    cfg, thr = world["cfg"], world["verified"].artifact.threshold
    assert thr == 0.34 and len(world["profiles"]) == 300
    pol = cfg.policy
    for prof, p in zip(world["profiles"], world["probs"], strict=True):
        assert prof.churn_probability == float(p) and 0 <= prof.churn_probability <= 1
        assert math.isfinite(prof.clv) and prof.clv >= 0 and prof.value_at_risk == pytest.approx(prof.clv * p)
        assert prof.risk_band in {b.name for b in cfg.risk_bands} and prof.currency == "INR"
        viable = [e for e in prof.action_evaluations
                  if e.action.action_id != "no_action" and e.eligible
                  and e.enb.expected_net_benefit > pol.min_expected_net_benefit]
        expect = INTERVENE if (p >= thr and prof.clv >= pol.min_customer_value and viable) else DO_NOT_INTERVENE
        assert prof.intervention_decision == expect
        if expect == INTERVENE:
            assert prof.expected_net_benefit == pytest.approx(max(e.enb.expected_net_benefit for e in viable))
            assert prof.expected_net_benefit > 0 and prof.recommended_action_id != "no_action"
        else:
            assert prof.recommended_action_id == "no_action" and prof.expected_net_benefit == 0
        assert prof.expected_net_benefit == pytest.approx(
            prof.value_at_risk * prof.action_success_rate - prof.action_cost)


def test_real_data_exercises_both_decisions_and_multiple_bands(world):
    decisions = {p.intervention_decision for p in world["profiles"]}
    assert decisions == {INTERVENE, DO_NOT_INTERVENE}
    assert len({p.risk_band for p in world["profiles"]}) >= 3
    assert all(p.clv_detail.lifetime_source.startswith("segment:") for p in world["profiles"])   # Contract present


def test_business_layer_scores_deterministically_and_serialises(world):
    again = world["engine"].profile_frame(world["customers"], world["probs"], "customerID")
    assert [p.to_dict() for p in again] == [p.to_dict() for p in world["profiles"]]
    json.dumps([p.to_dict() for p in world["profiles"]])


def test_what_if_on_a_real_customer_leaves_model_and_config_untouched(world):
    prof = max(world["profiles"], key=lambda p: p.value_at_risk)
    cfg = world["cfg"]
    r = simulate(cfg, prof.churn_probability, prof.clv,
                 Scenario(action_success_rate={prof.recommended_action_id: 0.01}), world["verified"].artifact.threshold)
    assert r.label == "SIMULATION / WHAT-IF" and r.delta["expected_net_benefit"] < 0
    assert load_business_config() == cfg
    assert (sha(MODEL), sha(META)) == world["before"]                         # model artifact byte-identical


def test_shap_explanation_feeds_a_separate_business_explanation(world, spec):
    v, engine = world["verified"], world["engine"]
    top = max(world["profiles"], key=lambda p: p.churn_probability)
    row = world["customers"][world["customers"]["customerID"] == top.customer_id]
    explainer = ChurnShapExplainer(v, load_train_background(CSV, spec, v))
    local = explainer.explain(row)
    ex = engine.explain(top, local, top_n=3).to_dict()
    assert set(ex) == {"MODEL EXPLANATION", "BUSINESS DECISION", "disclaimer"}
    named = [f.source_feature for f in local.features if f.direction == "increases_churn"][:3]
    assert named and all(n in ex["MODEL EXPLANATION"] for n in named)
    assert "not causes of churn" in ex["MODEL EXPLANATION"]
    assert abs(local.prediction_probability - top.churn_probability) < 1e-9     # same probability in both layers
    assert (sha(MODEL), sha(META)) == world["before"]


def test_no_test_split_customer_was_scored(world):
    test_ids = set(world["parts"].test["customerID"])
    assert not test_ids & {p.customer_id for p in world["profiles"]}
