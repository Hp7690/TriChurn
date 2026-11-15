"""App creation, OpenAPI, health / readiness / liveness, production safety guards."""
from __future__ import annotations

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from app import __version__
from app.core.config import ConfigurationError, Settings
from app.main import create_app
from app.services.adapters.factory import build_adapter
from app.services.adapters.phase15_adapter import Phase15Adapter
from app.services.adapters.unavailable import UnavailableAdapter
from tests.api.conftest import assert_error
from tests.support.fake_adapter import FakeAdapter

ENDPOINTS = {
    "/api/v1/health": "get", "/api/v1/readiness": "get", "/api/v1/liveness": "get",
    "/api/v1/predict": "post", "/api/v1/explain": "post", "/api/v1/business": "post",
    "/api/v1/segment": "post", "/api/v1/customer-intelligence": "post",
}


def test_create_app_returns_a_fastapi_application(client):
    assert isinstance(client.app, FastAPI) and client.app.title == "TriChurn API"
    assert client.app.version == __version__


def test_health(client):
    r = client.get("/api/v1/health")
    assert r.status_code == 200
    assert r.json() == {"status": "ok", "service": "trichurn-api", "api_version": "v1", "app_version": __version__,
                        "environment": "test"}


def test_liveness_never_depends_on_the_adapter(make_client):
    c = make_client(FakeAdapter(unavailable={"phase2_model", "business_engine", "explainability", "segmentation"}))
    assert c.get("/api/v1/liveness").json() == {"status": "alive"}


def test_readiness_ok(client):
    r = client.get("/api/v1/readiness")
    assert r.status_code == 200
    body = r.json()
    assert body["ready"] is True and {c["name"] for c in body["checks"]} == {
        "phase2_model", "business_engine", "explainability", "segmentation"}
    assert all(c["status"] == "ok" for c in body["checks"])


def test_readiness_503_when_any_capability_is_unavailable(make_client):
    r = make_client(FakeAdapter(unavailable={"explainability"})).get("/api/v1/readiness")
    assert r.status_code == 503
    body = r.json()
    assert body["ready"] is False
    assert {c["name"]: c["status"] for c in body["checks"]}["explainability"] == "unavailable"
    assert {c["name"]: c["status"] for c in body["checks"]}["phase2_model"] == "ok"


def test_openapi_and_docs_are_served(client):
    assert client.get("/docs").status_code == 200
    spec = client.get("/openapi.json").json()
    assert spec["openapi"].startswith("3.")
    for path, method in ENDPOINTS.items():
        assert method in spec["paths"][path], path
    schemas = spec["components"]["schemas"]
    assert {"CustomerRequest", "CustomerFeatures", "PredictionResponse", "ExplainResponse", "BusinessResponse",
            "SegmentResponse", "CustomerIntelligenceResponse", "ErrorResponse"} <= set(schemas)
    predict = spec["paths"]["/api/v1/predict"]["post"]
    assert predict["responses"]["422"]["content"]["application/json"]["schema"]["$ref"].endswith("/ErrorResponse")
    required = set(schemas["CustomerFeatures"]["required"])
    assert len(required) == 19 and "TotalCharges" in required          # every feature required, none defaulted
    assert schemas["CustomerFeatures"].get("additionalProperties") is False


def test_docs_can_be_disabled(adapter, tmp_path):
    c = TestClient(create_app(adapter, Settings(environment="test", project_root=tmp_path, enable_docs=False)))
    assert_error(c.get("/docs"), 404, "NOT_FOUND")
    assert_error(c.get("/openapi.json"), 404, "NOT_FOUND")


def test_unknown_route_and_wrong_method_use_the_error_envelope(client):
    assert_error(client.get("/api/v1/nope"), 404, "NOT_FOUND")
    assert_error(client.get("/api/v1/predict"), 405, "METHOD_NOT_ALLOWED")
    assert_error(client.post("/api/v1/health"), 405, "METHOD_NOT_ALLOWED")


# ------------------------------------------------------------------------------ production safety guards
def test_a_test_adapter_is_rejected_in_production(tmp_path):
    with pytest.raises(ConfigurationError, match="test adapter"):
        create_app(FakeAdapter(), Settings(environment="production", project_root=tmp_path))


def test_default_production_adapter_is_the_real_one_never_a_fake(tmp_path):
    app = create_app(settings=Settings(environment="production", project_root=tmp_path))
    adapter = app.state.services.adapter
    assert isinstance(adapter, Phase15Adapter) and adapter.is_test_double is False


def test_missing_integration_fails_closed_with_503(tmp_path, payload):
    s = Settings(environment="production", project_root=tmp_path, adapter_factory="no_such_pkg.mod:build")
    assert isinstance(build_adapter(s), UnavailableAdapter)
    c = TestClient(create_app(settings=s))
    assert c.get("/api/v1/readiness").status_code == 503
    assert c.get("/api/v1/liveness").status_code == 200
    for path in ("predict", "explain", "business", "segment", "customer-intelligence"):
        assert_error(c.post(f"/api/v1/{path}", json=payload), 503, "INTEGRATION_NOT_CONFIGURED")


def test_adapter_factory_must_return_a_port(tmp_path):
    s = Settings(environment="production", project_root=tmp_path, adapter_factory="builtins:dict")
    assert isinstance(build_adapter(s), UnavailableAdapter)          # dict(settings) is not a Phase15Port
    assert isinstance(build_adapter(Settings(project_root=tmp_path, adapter_factory="bad-format")), UnavailableAdapter)
