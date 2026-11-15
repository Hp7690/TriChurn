"""Integration: the complete 7,043-customer dataset through the REAL locked Phase 2/4/5 artifacts (batch path)."""
from __future__ import annotations

import hashlib
from pathlib import Path

import pytest

from retention.config import load_retention_config
from retention.errors import PortfolioUnavailableError
from retention.models import INTERVENE
from retention.prioritization import PriorityIndex
from retention.scoring import ArtifactPortfolioProvider, ScoringSources
from retention.summary import build_summary

ROOT = Path(__file__).resolve().parents[2]
PHASE2 = ROOT / "models" / "trichurn_churn_model_v2.0.0.joblib"
PHASE5 = ROOT / "models" / "trichurn_segmentation_v5.0.0.joblib"
CSV = ROOT / "ml" / "data" / "raw" / "telco_churn.csv"
SPEC = ROOT / "configs" / "datasets" / "telco.yaml"
LOCKED_PHASE2_SHA256 = "db399a55f650c6681e1caaf52257f909777e2c5fada3af5911370ddf5b8ff1ad"
LOCKED_PHASE5_SHA256 = "38423c9cf19b05aa35b72acd44ea3a8af4c3775a1e6cf2bb739ee1972dc05927"

pytestmark = pytest.mark.integration


def _sha(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _sources(model: Path = PHASE2, pin: str | None = LOCKED_PHASE2_SHA256) -> ScoringSources:
    return ScoringSources(model, pin, PHASE5, None, CSV, SPEC)


@pytest.fixture(scope="module")
def portfolio():
    if not all(p.is_file() for p in (PHASE2, PHASE5, CSV, SPEC)):
        pytest.skip("locked artifacts or dataset not present")
    return ArtifactPortfolioProvider(_sources()).get()


def test_locked_artifact_hashes_are_unchanged():
    assert _sha(PHASE2) == LOCKED_PHASE2_SHA256
    assert _sha(PHASE5) == LOCKED_PHASE5_SHA256


def test_whole_dataset_is_scored_in_batch(portfolio):
    assert len(portfolio.customers) == 7043
    assert len({c.customer_id for c in portfolio.customers}) == 7043
    assert portfolio.model_sha256 == LOCKED_PHASE2_SHA256 and portfolio.currency_code == "INR"
    assert portfolio.decision_threshold == 0.34
    assert all(0.0 <= c.churn_probability <= 1.0 for c in portfolio.customers)
    assert all(abs(c.value_at_risk - c.clv * c.churn_probability) < 1e-6 for c in portfolio.customers)
    assert {c.segment_name for c in portfolio.customers} == {
        "Low Value / High Risk", "Low Value / Stable", "High Value / Stable"}


def test_decisions_match_an_independent_phase4_recompute_for_a_sample(portfolio):
    import pandas as pd

    from ml.business import BusinessEngine, load_business_config
    from ml.pipelines.serialization import load_artifact

    artifact = load_artifact(PHASE2)
    engine = BusinessEngine(load_business_config(), float(artifact.threshold))
    raw = pd.read_csv(CSV)
    features = list(artifact.metadata["feature_names"])
    for position in range(0, len(raw), 281):                       # 26 evenly spread customers
        row = raw.iloc[[position]][features].copy()
        row["TotalCharges"] = pd.to_numeric(row["TotalCharges"], errors="coerce")
        p = float(artifact.predict_proba(row)[0])
        profile = engine.profile(p, row.iloc[0].to_dict(), str(raw.iloc[position]["customerID"]))
        got = portfolio.get(profile.customer_id)
        assert abs(got.churn_probability - p) < 1e-9
        assert got.decision == profile.intervention_decision
        assert got.recommended_action_id == profile.recommended_action_id
        assert abs(got.expected_net_benefit - profile.expected_net_benefit) < 1e-6


def test_summary_counts_match_the_portfolio(portfolio):
    index = PriorityIndex(portfolio, load_retention_config().priority)
    s = build_summary(portfolio, index)
    assert s.total_customers == 7043
    assert s.intervention_candidates == sum(1 for c in portfolio.customers if c.decision == INTERVENE)
    assert sum(b.customers for b in s.by_risk_band) == 7043
    assert sum(c.customers for c in s.recommended_campaigns) == s.intervention_candidates
    assert s.estimated_total_cost >= 0 and s.currency_code == "INR"


def test_the_pinned_hash_is_enforced_before_loading(tmp_path):
    tampered = tmp_path / "trichurn_churn_model_v2.0.0.joblib"
    tampered.write_bytes(PHASE2.read_bytes() + b"\x00")
    with pytest.raises(PortfolioUnavailableError) as exc:
        ArtifactPortfolioProvider(_sources(tampered)).get()
    assert exc.value.reason == "phase2_sha256_mismatch"


def test_missing_files_give_short_reason_codes(tmp_path):
    with pytest.raises(PortfolioUnavailableError) as exc:
        ArtifactPortfolioProvider(_sources(tmp_path / "nope.joblib")).get()
    assert exc.value.reason == "phase2_model_missing" and str(tmp_path) not in str(exc.value)


def test_scoring_does_not_modify_any_locked_file():
    before = (_sha(PHASE2), _sha(PHASE5), _sha(CSV))
    ArtifactPortfolioProvider(_sources()).get()
    assert before == (_sha(PHASE2), _sha(PHASE5), _sha(CSV))
