"""Phase 5 on the REAL locked churn model and the REAL Telco CSV (no synthetic data, nothing skipped by design).

Flow: Telco CSV -> split -> TRAIN customers -> locked Phase 2 probabilities -> Phase 4 BusinessEngine -> Phase 5.
The TEST split is never read; the Phase 2 artifact must be byte-identical afterwards.
"""
import hashlib
import json
import re
import subprocess
import sys
from dataclasses import asdict
from pathlib import Path

import numpy as np
import pandas as pd
import pytest

from ml.business import INTERVENE, BusinessEngine, load_business_config
from ml.config import load_config
from ml.explainability import load_verified_artifact
from ml.pipelines.ingestion import dataset_version, load_csv
from ml.pipelines.training import split_raw
from ml.segmentation import (
    assign_customers,
    build_metadata,
    clusterings_equivalent,
    fit_segmentation,
    load_segmentation_config,
    load_verified_segmentation_artifact,
    run_segmentation,
    save_segmentation_artifact,
)

ROOT = Path(__file__).resolve().parents[2]
MODEL = ROOT / "models/trichurn_churn_model_v2.0.0.joblib"
META = MODEL.with_name(f"{MODEL.stem}.metadata.json")
CSV = ROOT / "ml/data/raw/telco_churn.csv"
pytestmark = [pytest.mark.integration,
              pytest.mark.skipif(not (MODEL.exists() and CSV.exists()), reason="needs models/ and `make data`")]


def sha(p: Path) -> str:
    return hashlib.sha256(p.read_bytes()).hexdigest()


@pytest.fixture(scope="module")
def world(spec, training_cfg, features_cfg):
    before = (sha(MODEL), sha(META))
    verified = load_verified_artifact(MODEL)
    df = load_csv(CSV)
    sp = training_cfg["split"]
    parts = split_raw(df, spec, sp["val_size"], sp["test_size"], training_cfg["seed"])
    train = parts.train
    probs = verified.artifact.predict_proba(train)
    business, cfg = load_business_config(), load_segmentation_config()
    engine = BusinessEngine(business, verified.artifact.threshold)
    result = run_segmentation(train, probs, engine, spec, cfg, features_cfg, training_cfg)
    return {"before": before, "verified": verified, "parts": parts, "train": train, "probs": probs,
            "business": business, "cfg": cfg, "engine": engine, "result": result, "spec": spec,
            "features": features_cfg, "training": training_cfg, "df": df}


# ------------------------------------------------------------------------------------- data / leakage
def test_only_train_customers_are_segmented_and_test_is_never_read(world):
    res, parts = world["result"], world["parts"]
    ids = {a.customer_id for a in res.assignments}
    assert ids == set(parts.train["customerID"]) and len(ids) == len(parts.train)
    assert not ids & set(parts.test["customerID"]) and not ids & set(parts.val["customerID"])


def test_clustering_uses_exactly_the_documented_features_and_no_target(world):
    model = world["result"].model
    assert model.feature_names == ["tenure", "MonthlyCharges", "TotalCharges", "service_count", "contract_risk"]
    assert world["spec"].target not in model.feature_names
    assert model.centers.shape == (model.k, 5)


def test_target_and_probabilities_cannot_change_real_customer_segments(world):
    """Leakage proof on real data: scramble the churn labels AND the probabilities; the clusters are identical."""
    train, spec, cfg = world["train"], world["spec"], world["cfg"]
    scrambled = train.assign(Churn=np.random.default_rng(0).permutation(train["Churn"].to_numpy()))
    res = world["result"]
    model, _ = fit_segmentation(scrambled, spec, cfg, world["features"], res.seed)
    assert np.allclose(model.centers, res.model.centers, rtol=1e-12, atol=1e-12)
    assert np.array_equal(model.assign(scrambled)[0], res.segment_ids)
    noise = np.random.default_rng(1).uniform(0, 1, len(train))
    other = run_segmentation(scrambled, noise, world["engine"], spec, cfg, world["features"], world["training"])
    assert np.array_equal(other.segment_ids, res.segment_ids)
    assert [p.avg_churn_probability for p in other.profiles] != [p.avg_churn_probability for p in res.profiles]


# -------------------------------------------------------------------------------- K / determinism
def test_selected_k_follows_the_documented_rule(world):
    sel, cfg = world["result"].selection, world["cfg"].k_selection
    eligible = [c for c in sel.candidates if c.eligible]
    assert sel.selected_k == max(eligible, key=lambda c: (c.silhouette, -c.k)).k
    assert cfg.min_k <= sel.selected_k <= cfg.max_k == 6
    assert sel.best_silhouette_k == max(sel.candidates, key=lambda c: c.silhouette).k
    assert all(-1 <= c.silhouette <= 1 for c in sel.candidates)
    assert all(c.eligible == (cfg.min_k <= c.k <= cfg.max_k and c.min_cluster_share >= cfg.min_cluster_share)
               for c in sel.candidates)


def test_real_data_segmentation_is_reproducible_and_survives_label_permutation(world):
    train, spec, cfg, res = world["train"], world["spec"], world["cfg"], world["result"]
    again = run_segmentation(train, world["probs"], world["engine"], spec, cfg, world["features"], world["training"])
    assert np.array_equal(again.segment_ids, res.segment_ids)
    assert np.allclose(again.model.centers, res.model.centers, rtol=1e-12, atol=1e-12)
    assert [p.to_dict() for p in again.profiles] == [p.to_dict() for p in res.profiles]

# ----------------------------------------------------------------------------- Phase 4 integration
def test_profiles_aggregate_the_real_phase4_outputs(world):
    res, train, thr = world["result"], world["train"], world["verified"].artifact.threshold
    assert thr == 0.34 and len(res.business_profiles) == len(train)
    assert [b.churn_probability for b in res.business_profiles] == [float(p) for p in world["probs"]]
    lifetime = load_config("business")["clv"]["lifetime_months_by_segment"]
    clv = (train["MonthlyCharges"] * train["Contract"].map(lifetime)).to_numpy()          # independent of ml.business
    probs = np.asarray(world["probs"], dtype=float)
    for prof in res.profiles:
        m = res.segment_ids == prof.segment_id
        assert prof.customer_count == m.sum() and prof.customer_pct == pytest.approx(m.mean())
        assert prof.total_clv == pytest.approx(clv[m].sum()) and prof.avg_clv == pytest.approx(clv[m].mean())
        assert prof.total_value_at_risk == pytest.approx((clv[m] * probs[m]).sum())
        assert prof.avg_churn_probability == pytest.approx(probs[m].mean())
        assert prof.avg_tenure == pytest.approx(train.loc[m, "tenure"].mean())
        assert prof.avg_monthly_charges == pytest.approx(train.loc[m, "MonthlyCharges"].mean())
        total = pd.to_numeric(train.loc[m, "TotalCharges"], errors="coerce")
        assert prof.avg_total_charges == pytest.approx(total.mean())
        treated = [b for b, s in zip(res.business_profiles, res.segment_ids, strict=True)
                   if s == prof.segment_id and b.intervention_decision == INTERVENE]
        assert prof.intervention_rate == pytest.approx(len(treated) / m.sum())
        assert prof.total_enb == pytest.approx(sum(b.expected_net_benefit for b in treated))
    assert sum(p.customer_count for p in res.profiles) == len(train)


def test_strategies_come_from_phase4_actions_and_names_are_unique_and_rule_based(world):
    res, known = world["result"], set(world["business"].actions)
    names = [p.segment_name for p in res.profiles]
    assert len(set(names)) == len(names)
    pattern = re.compile(r"^(High|Mid|Low) Value / (High Risk|Moderate Risk|Stable)"
                         r"( \((New|Mid-Tenure|Established)\))?( #\d+)?$")
    assert all(pattern.match(n) for n in names), names
    for p in res.profiles:
        assert p.strategy.primary_action_id in known and set(p.strategy.action_mix) <= known
        assert (p.intervention_count == 0) == (p.strategy.primary_action_id == "no_action")
        assert sum(p.strategy.action_mix.values()) == p.intervention_count
    assert sorted(p.priority_rank for p in res.profiles) == list(range(1, len(res.profiles) + 1))
    top = min(res.profiles, key=lambda p: p.priority_rank)
    assert top.priority_score == max(p.priority_score for p in res.profiles)


def test_names_describe_the_measured_profile(world):
    res = world["result"]
    portfolio_clv = sum(p.total_clv for p in res.profiles) / sum(p.customer_count for p in res.profiles)
    naming, thr = world["cfg"].naming, world["verified"].artifact.threshold
    for p in res.profiles:
        ratio = p.avg_clv / portfolio_clv
        assert p.value_label == ("High Value" if ratio >= naming.value_high_min_ratio
                                 else "Low Value" if ratio <= naming.value_low_max_ratio else "Mid Value")
        assert p.risk_label == ("High Risk" if p.avg_churn_probability >= thr else
                                "Stable" if p.avg_churn_probability <= naming.risk_stable_max_probability
                                else "Moderate Risk")


def test_assignments_and_out_of_sample_validation_customers(world):
    res, parts = world["result"], world["parts"]
    assert all(a.distance_to_centroid >= 0 for a in res.assignments)
    names = {p.segment_id: p.segment_name for p in res.profiles}
    val = assign_customers(res.model, names, parts.val, "customerID")      # attributes only; no labels or outcomes
    share = pd.Series([a.segment_id for a in val]).value_counts(normalize=True).sort_index()
    train_share = pd.Series(res.segment_ids).value_counts(normalize=True).sort_index()
    assert (share - train_share).abs().max() < 0.06                          # same population, same segment mix


# -------------------------------------------------------------------------------------------- artifact
def test_artifact_roundtrip_on_real_data_and_phase2_artifact_untouched(world, tmp_path):
    res, cfg, train = world["result"], world["cfg"], world["train"]
    meta = build_metadata(res.model, cfg, res.seed, res.selection, res.profiles,
                          dataset_info={"path": "ml/data/raw/telco_churn.csv", "version": dataset_version(CSV),
                                        "rows": len(world["df"])},
                          split_sizes={"train": len(train)}, n_train_customers=len(train),
                          business_config=asdict(world["business"]), churn_model_sha256=world["verified"].sha256)
    paths = save_segmentation_artifact(res.model, meta, tmp_path, cfg.artifact_name)
    loaded = load_verified_segmentation_artifact(paths.model)
    assert np.array_equal(loaded.model.assign(train)[0], res.segment_ids)
    assert loaded.metadata["profiling_provenance"]["churn_model_sha256"] == world["verified"].sha256
    assert clusterings_equivalent(loaded.model.assign(train)[0], res.segment_ids)
    assert (sha(MODEL), sha(META)) == world["before"]


def run_script(*extra: str) -> subprocess.CompletedProcess:
    return subprocess.run([sys.executable, str(ROOT / "scripts/run_phase5.py"), *extra], cwd=ROOT,
                          capture_output=True, text=True, timeout=900, check=False)


def segmentation_section(stdout: str) -> str:
    """The deterministic part of the script output (before artifact paths are printed)."""
    return stdout.split("\nArtifact:")[0].split("\nPhase 2 churn artifact")[0]


def test_phase5_entry_script_saves_a_verifiable_artifact_and_report(tmp_path, world):
    res = run_script("--out-dir", str(tmp_path))
    assert res.returncode == 0, res.stderr + res.stdout
    assert "Reproducible (refit with same seed gives identical assignments): True" in res.stdout
    assert "Phase 2 churn artifact unchanged: True" in res.stdout and "TEST never read" in res.stdout
    report = json.loads((tmp_path / "phase5_report.json").read_text())
    assert report["split_used"].startswith("TRAIN") and report["reproducible"] is True
    assert report["churn_model_sha256"] == sha(MODEL) and report["model_threshold"] == 0.34
    loaded = load_verified_segmentation_artifact(tmp_path / "trichurn_segmentation_v5.0.0.joblib")
    assert loaded.sha256 == report["artifact"]["sha256"] and loaded.model.k == report["selected_k"]
    assert [s["segment_name"] for s in report["segments"]] and set(report["validation_assignment_shares"]) == {
        s["segment_name"] for s in report["segments"]}
    assert sha(MODEL) == report["churn_model_sha256"] == json.loads(META.read_text())["artifact_sha256"]
    assert (sha(MODEL), sha(META)) == world["before"]


def test_script_output_does_not_depend_on_test_split_features(tmp_path, world):
    """Corrupt ONLY the test rows' features (labels untouched, so the stratified split is unchanged) and re-run
    the real entry script: the segmentation and its profiles must be identical."""
    test_ids = set(world["parts"].test["customerID"])
    df = pd.read_csv(CSV, dtype=str, keep_default_na=False)
    mask = df["customerID"].isin(test_ids)
    df.loc[mask, ["tenure", "MonthlyCharges", "TotalCharges"]] = ["0", "9000000", "garbage"]
    df.loc[mask, "Contract"] = "Two year"
    corrupted = tmp_path / "telco_corrupted_test_rows.csv"
    df.to_csv(corrupted, index=False)
    original = run_script("--no-save")
    altered = run_script("--no-save", "--csv", str(corrupted))
    assert original.returncode == 0 and altered.returncode == 0, altered.stderr + altered.stdout
    assert segmentation_section(original.stdout) == segmentation_section(altered.stdout)
    assert "Segments (ordered by priority" in original.stdout
