"""HTTP tests for the Phase 9 endpoints. Self-contained: a tiny in-file adapter double and a synthetic portfolio (the
real Phase 1-5 wiring is covered by tests/retention/test_real_portfolio.py). Requires fastapi + httpx."""
from __future__ import annotations

import pytest
from fastapi.testclient import TestClient

from app.core.config import API_PREFIX, Settings
from app.core.errors import ApiError, ErrorCode
from app.core.retention_settings import RetentionSettings
from app.main import create_app
from app.services.adapters.interface import (
    CheckResult,
    ExplanationResult,
    FeatureContribution,
    ReadinessReport,
)
from app.services.retention_service import RetentionService
from retention.errors import PortfolioUnavailableError
from tests.retention.support import StaticProvider, make_portfolio

BASE = f"{API_PREFIX}/retention"
PF = make_portfolio(100)


class _Adapter:
    """Minimal Phase15Port double: only ``explain`` is used by Phase 9."""

    is_test_double = True

    def __init__(self, explain_fails: bool = False):
        self.explain_fails = explain_fails

    def warm_up(self) -> None:
        return None

    def readiness(self) -> ReadinessReport:
        return ReadinessReport((CheckResult("x", True, "ok"),))

    def predict(self, customer):
        raise NotImplementedError

    def business(self, customer, churn_probability=None, explanation=None):
        raise NotImplementedError

    def segment(self, customer):
        raise NotImplementedError

    def explain(self, customer):
        if self.explain_fails:
            raise ApiError(ErrorCode.CAPABILITY_UNAVAILABLE, "unavailable", 503)
        return ExplanationResult(
            0.5, 1, 0.34, -1.0, "log_odds", 0.0, 0.0,
            [FeatureContribution("Contract", "Month-to-month", 0.4, "increases_churn"),
             FeatureContribution("tenure", 2, 0.3, "increases_churn"),
             FeatureContribution("TechSupport", "Yes", -0.2, "decreases_churn")], "interp", "2.0.0")


def _client(provider=None, adapter=None) -> TestClient:
    settings = Settings(environment="test")
    adapter = adapter or _Adapter()
    app = create_app(adapter=adapter, settings=settings)
    app.state.retention = RetentionService(settings, RetentionSettings(database_path=":memory:"), adapter,
                                           provider or StaticProvider(PF))
    return TestClient(app)


@pytest.fixture
def client() -> TestClient:
    return _client()


def _error(response, status, code):
    assert response.status_code == status, response.text
    body = response.json()
    assert set(body) == {"error"} and body["error"]["code"] == code
    for forbidden in ("Traceback", "/home/", "C:\\", ".joblib", "sqlite"):
        assert forbidden not in response.text
    return body["error"]


def test_existing_routes_are_still_registered(client):
    paths = set(client.get("/openapi.json").json()["paths"])
    for p in ("/health", "/liveness", "/readiness", "/predict", "/explain", "/business", "/segment",
              "/customer-intelligence"):
        assert f"{API_PREFIX}{p}" in paths
    assert any(p.startswith(BASE) for p in paths)


def test_summary(client):
    body = client.get(f"{BASE}/summary").json()
    assert body["kind"] == "estimate" and body["total_customers"] == 100
    assert body["currency_code"] == "INR" and "ASSUMED" in body["note"]
    assert body["top_priorities"][0]["rank"] == 1 and body["top_priorities"][0]["reasons"] == []


def test_priorities_pagination_and_filters(client):
    body = client.get(f"{BASE}/priorities", params={"page": 2, "page_size": 10}).json()
    assert body["page"] == 2 and len(body["items"]) == 10 and body["total"] == 100 and body["page_count"] == 10
    assert all(item["reasons"] for item in body["items"]) and "not a probability" in body["score_note"]
    high = client.get(f"{BASE}/priorities", params={"risk_band": "HIGH", "page_size": 200}).json()
    assert high["items"] and all(i["customer"]["risk_band"] == "HIGH" for i in high["items"])
    p1 = client.get(f"{BASE}/priorities", params={"tier": "MONITOR", "page_size": 200}).json()
    assert all(i["customer"]["decision"] == "DO_NOT_INTERVENE" for i in p1["items"])


@pytest.mark.parametrize("params", [{"page": 0}, {"page_size": 201}, {"sort_by": "bogus"}, {"tier": "P9"},
                                    {"min_churn_probability": 2}, {"decision": "MAYBE"}])
def test_priorities_reject_invalid_parameters(client, params):
    _error(client.get(f"{BASE}/priorities", params=params), 422, "INVALID_INPUT")


def test_actions_come_from_the_phase4_catalogue(client):
    ids = {a["action_id"] for a in client.get(f"{BASE}/actions").json()["actions"]}
    assert "discount_offer" in ids and "no_action" not in ids


def test_recommendation_with_and_without_explainability():
    candidate = next(c for c in PF.customers if c.decision == "INTERVENE")
    with_shap = _client().get(f"{BASE}/customers/{candidate.customer_id}/recommendation").json()
    assert with_shap["explainability_available"] is True and with_shap["drivers"][0]["feature"] == "Contract"
    assert all(d["direction"] == "increases_churn" for d in with_shap["drivers"])
    assert with_shap["primary_action"]["action_id"] == candidate.recommended_action_id
    assert with_shap["causal_claim"] is False and with_shap["uplift_available"] is False
    plain = _client(adapter=_Adapter(explain_fails=True)).get(
        f"{BASE}/customers/{candidate.customer_id}/recommendation").json()
    assert plain["explainability_available"] is False and plain["drivers"] == []


def test_recommendation_unknown_customer_and_bad_id(client):
    _error(client.get(f"{BASE}/customers/NOPE/recommendation"), 404, "NOT_FOUND")
    _error(client.get(f"{BASE}/customers/bad%20id%3B/recommendation"), 422, "INVALID_INPUT")


def test_simulate_and_compare(client):
    scenarios = [{"action_id": "discount_offer"},
                 {"action_id": "loyalty_offer", "success_rate_override": 0.2, "top_n": 20}]
    body = client.post(f"{BASE}/simulate", json={"scenarios": scenarios}).json()
    assert len(body["results"]) == 2 and body["label"] == "ESTIMATE"
    assert body["results"][1]["success_rate_source"] == "scenario_override"
    assert body["best_by_net_benefit_index"] in (0, 1)


@pytest.mark.parametrize("payload", [
    {"scenarios": []},
    {"scenarios": [{"action_id": "discount_offer", "success_rate_override": 1.5}]},
    {"scenarios": [{"action_id": "discount_offer", "surprise": 1}]},
    {"scenarios": [{"action_id": "no_action"}]},
    {"scenarios": [{"action_id": "ghost"}]},
    {"scenarios": [{"action_id": "discount_offer"}] * 11},
    {"scenarios": [{"action_id": "bad id!"}]},
])
def test_simulate_rejects_invalid_scenarios(client, payload):
    _error(client.post(f"{BASE}/simulate", json=payload), 422, "INVALID_INPUT")


def test_campaigns_start_empty(client):
    assert client.get(f"{BASE}/campaigns").json() == {"campaigns": []}
    a = client.get(f"{BASE}/analytics").json()
    assert a["campaigns"] == [] and a["total_assigned"] == 0 and a["total_actual_cost"] is None


def test_campaign_lifecycle(client):
    created = client.post(f"{BASE}/campaigns", json={
        "name": "Win-back", "action_id": "discount_offer", "campaign_date": "2025-03-01"})
    assert created.status_code == 201
    cid = created.json()["campaign_id"]
    eligible = [c.customer_id for c in PF.customers
                if next(o for o in c.options if o.action_id == "discount_offer").eligible][:3]

    assigned = client.post(f"{BASE}/campaigns/{cid}/assignments", json={"customer_ids": eligible + ["GHOST-1"]}).json()
    assert assigned["assigned"] == 3 and assigned["unknown_customer_ids"] == ["GHOST-1"]
    again = client.post(f"{BASE}/campaigns/{cid}/assignments", json={"customer_ids": eligible[:1]}).json()
    assert again["assigned"] == 0 and again["already_assigned_ids"] == eligible[:1]

    outcome = {"outcomes": [{"customer_id": eligible[0], "outcome": "retained", "actual_cost": 55,
                             "actual_retained_revenue": 400}]}
    assert client.post(f"{BASE}/campaigns/{cid}/outcomes", json=outcome).json()["recorded"] == 1
    repeat = client.post(f"{BASE}/campaigns/{cid}/outcomes", json=outcome).json()
    assert repeat["recorded"] == 0 and repeat["already_recorded_ids"] == [eligible[0]]

    metrics = client.get(f"{BASE}/campaigns/{cid}").json()
    assert metrics["assigned"] == 3 and metrics["outcomes_recorded"] == 1
    assert metrics["actual_retained_revenue"] == 400 and metrics["estimated_benefit"] > 0
    assert "no uplift is claimed" in metrics["note"]
    assert client.get(f"{BASE}/analytics").json()["total_assigned"] == 3
    assert len(client.get(f"{BASE}/campaigns").json()["campaigns"]) == 1


@pytest.mark.parametrize("payload", [
    {"name": "", "action_id": "discount_offer", "campaign_date": "2025-03-01"},
    {"name": "x", "action_id": "no_action", "campaign_date": "2025-03-01"},
    {"name": "x", "action_id": "discount_offer", "campaign_date": "2025-99-99"},
    {"name": "x", "action_id": "discount_offer", "campaign_date": "2025-03-01", "extra": True},
])
def test_campaign_creation_validation(client, payload):
    _error(client.post(f"{BASE}/campaigns", json=payload), 422, "INVALID_INPUT")


def test_assignment_and_outcome_validation(client):
    cid = client.post(f"{BASE}/campaigns", json={
        "name": "x", "action_id": "discount_offer", "campaign_date": "2025-03-01"}).json()["campaign_id"]
    _error(client.post(f"{BASE}/campaigns/{cid}/assignments", json={"customer_ids": []}), 422, "INVALID_INPUT")
    _error(client.post(f"{BASE}/campaigns/{cid}/assignments", json={"customer_ids": ["a"], "group": "vip"}),
           422, "INVALID_INPUT")
    _error(client.post(f"{BASE}/campaigns/{cid}/outcomes",
                       json={"outcomes": [{"customer_id": "a", "outcome": "won"}]}), 422, "INVALID_INPUT")
    _error(client.post(f"{BASE}/campaigns/{cid}/outcomes",
                       json={"outcomes": [{"customer_id": "a", "outcome": "retained", "actual_cost": -5}]}),
           422, "INVALID_INPUT")
    _error(client.post(f"{BASE}/campaigns/cmp_missing/assignments", json={"customer_ids": ["a"]}), 404, "NOT_FOUND")
    _error(client.post(f"{BASE}/campaigns/cmp_missing/outcomes",
                       json={"outcomes": [{"customer_id": "a", "outcome": "retained"}]}), 404, "NOT_FOUND")
    _error(client.get(f"{BASE}/campaigns/cmp_missing"), 404, "NOT_FOUND")


def test_uplift_readiness_reports_not_ready_and_claims_no_model(client):
    body = client.get(f"{BASE}/uplift-readiness").json()
    assert body["ready"] is False and body["status"] == "NOT_READY"
    assert body["treatment_assignments"] == 0 and body["control_assignments"] == 0
    assert "No uplift model exists" in body["note"]


def test_unavailable_portfolio_returns_503_without_leaking_details():
    client = _client(provider=StaticProvider(error=PortfolioUnavailableError("phase2_sha256_mismatch")))
    err = _error(client.get(f"{BASE}/summary"), 503, "CAPABILITY_UNAVAILABLE")
    assert "phase2" not in err["message"]
    assert client.get(f"{BASE}/campaigns").json() == {"campaigns": []}         # campaign tracking still works
    assert client.get(f"{BASE}/uplift-readiness").status_code == 200
