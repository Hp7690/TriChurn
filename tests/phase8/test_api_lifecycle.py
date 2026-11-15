"""FastAPI compatibility: every Phase 6 endpoint still works, and the additive lifecycle endpoint reports honestly."""
from __future__ import annotations

import copy

import pandas as pd
import pytest
from fastapi.testclient import TestClient

from app.core.config import Settings
from app.main import create_app
from app.schemas.common import CustomerRequest
from mlops.loading import load_verified_model
from mlops.registry import register_verified_model
from mlops.tracking import log_model_run
from tests.phase8.conftest import LOCKED, ROOT, store_settings
from tests.support.fake_adapter import FakeAdapter

EXAMPLE = CustomerRequest.model_config["json_schema_extra"]["example"]
ORIGINAL_ENDPOINTS = {("get", "/api/v1/health"), ("get", "/api/v1/liveness"), ("get", "/api/v1/readiness"),
                      ("post", "/api/v1/predict"), ("post", "/api/v1/explain"), ("post", "/api/v1/business"),
                      ("post", "/api/v1/segment"), ("post", "/api/v1/customer-intelligence")}
URL = "/api/v1/model/lifecycle"
RETENTION_ENDPOINTS = {
    ("get", "/api/v1/retention/summary"),
    ("get", "/api/v1/retention/priorities"),
    ("get", "/api/v1/retention/actions"),
    ("get", "/api/v1/retention/customers/{customer_id}/recommendation"),
    ("post", "/api/v1/retention/simulate"),
    ("post", "/api/v1/retention/campaigns"),
    ("get", "/api/v1/retention/campaigns"),
    ("get", "/api/v1/retention/campaigns/{campaign_id}"),
    ("post", "/api/v1/retention/campaigns/{campaign_id}/assignments"),
    ("post", "/api/v1/retention/campaigns/{campaign_id}/outcomes"),
    ("get", "/api/v1/retention/analytics"),
    ("get", "/api/v1/retention/uplift-readiness"),
}


@pytest.fixture(autouse=True)
def clean_env(monkeypatch):
    for var in ("MLFLOW_TRACKING_URI", "TRICHURN_MODEL_SHA256", "TRICHURN_MODEL_PATH", "MLFLOW_MODEL_VERSION"):
        monkeypatch.delenv(var, raising=False)


def make_client(root=ROOT) -> TestClient:
    return TestClient(create_app(adapter=FakeAdapter(), settings=Settings(environment="test", project_root=root)))


def test_original_endpoints_and_phase9_routes_are_additive():
    paths = make_client().get("/openapi.json").json()["paths"]
    served = {(method, path) for path, ops in paths.items() for method in ops}
    assert ORIGINAL_ENDPOINTS <= served
    assert {("get", URL)} | RETENTION_ENDPOINTS <= served


def test_original_endpoints_keep_their_contracts():
    client = make_client()
    health = client.get("/api/v1/health").json()
    assert set(health) == {"status", "service", "api_version", "app_version", "environment"}
    assert health["status"] == "ok"
    assert client.get("/api/v1/liveness").json() == {"status": "alive"}
    ready = client.get("/api/v1/readiness")
    assert ready.status_code == 200 and set(ready.json()) == {"ready", "checks", "details"}
    r = client.post("/api/v1/predict", json=copy.deepcopy(EXAMPLE))
    assert r.status_code == 200 and set(r.json()) == {
        "customer_id", "churn_probability", "predicted_churn", "predicted_label", "decision_threshold", "risk_band",
        "model_name", "model_version"}


def test_lifecycle_reports_a_verified_model_with_no_registry_configured():
    body = make_client().get(URL).json()
    assert body["status"] == "verified" and body["model_version"] == "2.0.0"
    assert body["integrity"]["ok"]
    assert body["integrity"]["actual_sha256"] == body["integrity"]["expected_sha256"] == LOCKED
    assert body["registry"]["status"] == "not_configured"


def test_lifecycle_never_leaks_filesystem_paths():
    text = make_client().get(URL).text
    for forbidden in (str(ROOT), "/home/", "C:\\", "Traceback", "site-packages"):
        assert forbidden not in text


def test_a_wrong_pin_is_reported_clearly_and_other_endpoints_keep_working(monkeypatch):
    monkeypatch.setenv("TRICHURN_MODEL_SHA256", "d" * 64)
    client = make_client()
    body = client.get(URL).json()
    assert client.get(URL).status_code == 200
    assert body["status"] == "integrity_failed" and body["integrity"]["reason"] == "sha256_mismatch"
    assert body["integrity"]["actual_sha256"] == LOCKED
    assert client.post("/api/v1/predict", json=copy.deepcopy(EXAMPLE)).status_code == 200


def test_a_missing_model_is_reported(tmp_path):
    body = make_client(tmp_path).get(URL).json()
    assert body["status"] == "model_missing" and body["integrity"]["reason"] == "missing"
    assert str(tmp_path) not in str(body)


def test_malformed_configuration_is_reported_without_echoing_it(monkeypatch):
    monkeypatch.setenv("TRICHURN_MODEL_SHA256", "not-a-digest")
    response = make_client().get(URL)
    assert response.status_code == 200 and response.json()["status"] == "misconfigured"
    assert "not-a-digest" not in response.text


def test_registry_state_is_exposed_when_a_registry_is_configured(tmp_path, monkeypatch):
    store = store_settings(tmp_path / "s")
    register_verified_model(store, log_model_run(store).run_id)
    monkeypatch.setenv("MLFLOW_TRACKING_URI", store.effective_tracking_uri)
    reg = make_client().get(URL).json()["registry"]
    assert reg["status"] == "registered" and reg["alias"] == "production" and reg["semantic_version"] == "2.0.0"
    assert reg["matches_pinned_sha256"] is True


def test_an_unreachable_registry_does_not_break_the_endpoint(monkeypatch):
    monkeypatch.setenv("MLFLOW_TRACKING_URI", "http://127.0.0.1:9")
    monkeypatch.setenv("MLFLOW_HTTP_REQUEST_MAX_RETRIES", "0")
    monkeypatch.setenv("MLFLOW_HTTP_REQUEST_TIMEOUT", "2")
    response = make_client().get(URL)
    assert response.status_code == 200 and response.json()["status"] == "verified"
    assert response.json()["registry"]["status"] == "unavailable" and "127.0.0.1" not in response.text


def test_real_app_prediction_equals_the_mlops_loaded_model_bit_for_bit():
    """Real Phase 1-5 wiring (no fake): the API's probability is the locked model's probability."""
    client = TestClient(create_app())
    expected = float(load_verified_model(__import__("mlops").MlopsSettings()).artifact.predict_proba(
        pd.DataFrame([EXAMPLE["features"]]))[0])
    first = client.post("/api/v1/predict", json=copy.deepcopy(EXAMPLE))
    second = client.post("/api/v1/predict", json=copy.deepcopy(EXAMPLE))
    assert first.status_code == 200 and first.json() == second.json()
    assert first.json()["churn_probability"] == pytest.approx(expected, abs=1e-12)
    assert first.json()["decision_threshold"] == 0.34 and first.json()["model_version"] == "2.0.0"
