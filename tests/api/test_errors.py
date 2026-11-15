"""Error handling: nothing internal is ever exposed."""
from __future__ import annotations

import logging

import pytest

from app.core.errors import ApiError, ErrorCode, sanitize_validation_errors
from tests.api.conftest import assert_error
from tests.support.fake_adapter import FakeAdapter

SECRET = r"C:\Users\ASUS\secret\models\trichurn_churn_model_v2.0.0.joblib; TRICHURN_TOKEN=abc123"
ENDPOINTS = ["predict", "explain", "business", "segment", "customer-intelligence"]


@pytest.mark.parametrize("op, endpoint", [("predict", "predict"), ("explain", "explain"), ("business", "business"),
                                         ("segment", "segment"), ("predict", "customer-intelligence")])
def test_unexpected_exceptions_become_an_opaque_500(make_client, payload, caplog, op, endpoint):
    c = make_client(FakeAdapter(raises={op: RuntimeError(SECRET)}))
    with caplog.at_level(logging.ERROR, logger="trichurn.api"):
        r = c.post(f"/api/v1/{endpoint}", json=payload)
    err = assert_error(r, 500, "INTERNAL_ERROR")
    assert err["message"] == "An internal error occurred." and len(err["error_id"]) == 12
    for leaked in ("ASUS", "secret", "TRICHURN_TOKEN", "abc123", "RuntimeError"):
        assert leaked not in r.text
    assert err["error_id"] in caplog.text and "RuntimeError" in caplog.text    # but it IS logged server-side


def test_api_errors_raised_by_the_adapter_pass_through_unchanged(make_client, payload):
    boom = ApiError(ErrorCode.ARTIFACT_UNAVAILABLE, "The 'model' artifact is unavailable or failed verification.", 503)
    err = assert_error(make_client(FakeAdapter(raises={"predict": boom})).post("/api/v1/predict", json=payload), 503,
                       "ARTIFACT_UNAVAILABLE")
    assert "model" in err["message"]


def test_last_resort_handler_for_errors_outside_the_services(make_client):
    class Exploding(FakeAdapter):
        def readiness(self):
            raise RuntimeError(SECRET)

    r = make_client(Exploding(), raise_server_exceptions=False).get("/api/v1/readiness")
    err = assert_error(r, 500, "INTERNAL_ERROR")
    assert "ASUS" not in r.text and err["error_id"]


def test_validation_details_contain_field_and_message_only():
    raw = {"loc": ("body", "features", "tenure"), "msg": "Input should be a valid integer", "type": "int_type",
           "input": "SECRET", "ctx": {"error": "C:\\x"}}
    cleaned = sanitize_validation_errors([raw])
    assert cleaned == [{"field": "features.tenure", "message": "Input should be a valid integer"}]


@pytest.mark.parametrize("endpoint", ENDPOINTS)
def test_validation_errors_use_the_same_envelope_on_every_endpoint(client, endpoint):
    err = assert_error(client.post(f"/api/v1/{endpoint}", json={"features": {"tenure": "x"}}), 422, "INVALID_INPUT")
    assert err["message"] == "Invalid customer features." and err["details"]


def test_error_envelope_example_from_the_spec(client):
    r = client.post("/api/v1/predict", json={"features": {}})
    assert r.json()["error"]["code"] == "INVALID_INPUT" and r.json()["error"]["message"] == "Invalid customer features."
