"""Phase 4 on the real model + real Telco data, verified WITHOUT calling ml.business for the expected values.

The expected CLV, value at risk, ENB, decision and action are recomputed here from the raw CSV, the locked model's
probability and the YAML numbers using plain arithmetic.
"""
import json
import subprocess
import sys
from pathlib import Path

import pytest

from ml.business import BusinessEngine, load_business_config
from ml.config import load_config
from ml.explainability import load_verified_artifact
from ml.pipelines.ingestion import load_csv
from ml.pipelines.training import split_raw

ROOT = Path(__file__).resolve().parents[2]
MODEL = ROOT / "models/trichurn_churn_model_v2.0.0.joblib"
CSV = ROOT / "ml/data/raw/telco_churn.csv"
pytestmark = [pytest.mark.integration,
              pytest.mark.skipif(not (MODEL.exists() and CSV.exists()), reason="needs models/ and `make data`")]


@pytest.fixture(scope="module")
def world(spec, training_cfg):
    verified = load_verified_artifact(MODEL)
    parts = split_raw(load_csv(CSV), spec, training_cfg["split"]["val_size"], training_cfg["split"]["test_size"],
                      training_cfg["seed"])
    customers = parts.train.head(400)
    probs = verified.artifact.predict_proba(customers)
    engine = BusinessEngine(load_business_config(), verified.artifact.threshold)
    return customers, probs, engine.profile_frame(customers, probs, spec.id_column), verified


def test_business_outputs_equal_plain_arithmetic_from_yaml_and_the_model_probability(world):
    customers, probs, profiles, verified = world
    raw = load_config("business")
    lifetime, pol = raw["clv"]["lifetime_months_by_segment"], raw["policy"]
    assert raw["clv"]["monthly_discount_rate"] == 0 and raw["clv"]["gross_margin"] == 1.0
    thr = verified.artifact.threshold
    for (_, row), p, prof in zip(customers.iterrows(), probs, profiles, strict=True):
        clv = float(row["MonthlyCharges"]) * lifetime[row["Contract"]]          # CLV = revenue x assumed lifetime
        assert prof.clv == pytest.approx(clv)
        assert prof.value_at_risk == pytest.approx(clv * float(p))
        best_id, best_enb = None, pol["min_expected_net_benefit"]
        for aid, a in raw["actions"].items():
            if aid == "no_action" or not a["enabled"] or clv < a.get("min_clv", 0):
                continue
            enb = clv * float(p) * a["success_rate"] - a["cost"]
            if enb > best_enb or (enb == best_enb and best_id is None):
                best_id, best_enb = aid, enb
        intervene = float(p) >= thr and clv >= pol["min_customer_value"] and best_id is not None
        assert (prof.intervention_decision == "INTERVENE") == intervene
        assert prof.recommended_action_id == (best_id if intervene else "no_action")
        if intervene:
            assert prof.expected_net_benefit == pytest.approx(best_enb)


def test_business_layer_uses_the_locked_models_probability_not_a_second_model(world):
    customers, probs, profiles, verified = world
    assert [p.churn_probability for p in profiles] == [float(x) for x in probs]
    assert verified.artifact.metadata["model_name"] == "logistic_regression" and verified.artifact.threshold == 0.34


def test_phase4_entry_script_runs_end_to_end(tmp_path):
    out = tmp_path / "summary.json"
    res = subprocess.run([sys.executable, str(ROOT / "scripts/run_phase4.py"), "--n", "80", "--out", str(out)],
                         cwd=ROOT, capture_output=True, text=True, timeout=300, check=False)
    assert res.returncode == 0, res.stderr + res.stdout
    summary = json.loads(out.read_text())
    assert summary["customers_scored"] == 80 and summary["model_threshold"] == 0.34
    assert "MODEL EXPLANATION" in res.stdout and "BUSINESS DECISION" in res.stdout
