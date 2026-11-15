"""POST /api/v1/predict and request validation (strict, nothing defaulted, nothing echoed)."""
from __future__ import annotations

import json

import pytest

from tests.api.conftest import FEATURE_NAMES, assert_error

URL = "/api/v1/predict"


def test_predict_response_shape(client, payload):
    r = client.post(URL, json=payload)
    assert r.status_code == 200
    body = r.json()
    assert set(body) == {"customer_id", "churn_probability", "predicted_churn", "predicted_label", "decision_threshold",
                         "risk_band", "model_name", "model_version"}
    assert body["customer_id"] == "EXAMPLE-0001" and 0.0 <= body["churn_probability"] <= 1.0
    assert body["predicted_churn"] == (body["churn_probability"] >= body["decision_threshold"])
    assert body["predicted_label"] == ("CHURN" if body["predicted_churn"] else "NO_CHURN")
    assert body["decision_threshold"] == 0.34 and body["model_version"] and body["risk_band"]


def test_customer_id_is_optional(client, payload):
    del payload["customer_id"]
    assert client.post(URL, json=payload).json()["customer_id"] is None


def test_adapter_receives_exactly_the_validated_features_and_nothing_else(client, adapter, payload):
    client.post(URL, json=payload)
    (op, args), = adapter.calls
    assert op == "predict" and args["customer"] == payload["features"]
    assert set(args["customer"]) == set(FEATURE_NAMES) and len(FEATURE_NAMES) == 19


@pytest.mark.parametrize("name", FEATURE_NAMES)
def test_every_feature_is_required_and_nothing_is_defaulted(client, adapter, payload, name):
    del payload["features"][name]
    err = assert_error(client.post(URL, json=payload), 422, "INVALID_INPUT")
    assert err["message"] == "Invalid customer features."
    assert any(d["field"] == f"features.{name}" for d in err["details"])
    assert adapter.calls == []                          # the model was never called with an invented value


def test_missing_features_object_and_empty_body(client, adapter):
    assert_error(client.post(URL, json={"customer_id": "x"}), 422, "INVALID_INPUT")
    assert_error(client.post(URL, json={}), 422, "INVALID_INPUT")
    assert_error(client.post(URL, content=b""), 422, "INVALID_INPUT")
    assert adapter.calls == []


def test_invalid_json_and_wrong_content_type(client):
    assert_error(client.post(URL, content=b"{not json", headers={"Content-Type": "application/json"}), 422,
                 "INVALID_INPUT")
    assert_error(client.post(URL, content=b"hello", headers={"Content-Type": "text/plain"}), 422, "INVALID_INPUT")


@pytest.mark.parametrize("mutation", [
    {"Contract": "Weekly"}, {"gender": "Other"}, {"Partner": "yes"}, {"InternetService": "Cable"},
    {"OnlineSecurity": "Maybe"}, {"MultipleLines": "No internet service"}, {"PaymentMethod": "Cash"},
    {"tenure": -1}, {"tenure": "10"}, {"tenure": 10.5}, {"tenure": None},
    {"MonthlyCharges": -0.01}, {"MonthlyCharges": "29.75"}, {"MonthlyCharges": None}, {"TotalCharges": -5},
    {"TotalCharges": "301.9"}, {"SeniorCitizen": 2}, {"SeniorCitizen": True}, {"SeniorCitizen": "1"},
    {"SeniorCitizen": 1.0},
])
def test_invalid_values_are_rejected_without_coercion(client, adapter, payload, mutation):
    payload["features"].update(mutation)
    err = assert_error(client.post(URL, json=payload), 422, "INVALID_INPUT")
    assert err["details"] and adapter.calls == []


@pytest.mark.parametrize("raw", ["NaN", "Infinity", "-Infinity"])
def test_non_finite_numbers_are_rejected(client, adapter, payload, raw):
    body = json.dumps(payload).replace('"MonthlyCharges": 29.75', f'"MonthlyCharges": {raw}')
    assert_error(client.post(URL, content=body, headers={"Content-Type": "application/json"}), 422, "INVALID_INPUT")
    assert adapter.calls == []


def test_unknown_fields_are_rejected_everywhere(client, adapter, payload):
    payload["features"]["Churn"] = "Yes"                                  # the target must never be accepted
    assert_error(client.post(URL, json=payload), 422, "INVALID_INPUT")
    del payload["features"]["Churn"]
    payload["churn_probability"] = 0.99                                    # clients cannot inject a probability
    assert_error(client.post(URL, json=payload), 422, "INVALID_INPUT")
    assert adapter.calls == []


def test_total_charges_null_is_only_for_brand_new_customers(client, adapter, payload):
    payload["features"].update(TotalCharges=None)                          # tenure 10 -> invalid
    err = assert_error(client.post(URL, json=payload), 422, "INVALID_INPUT")
    assert "TotalCharges" in json.dumps(err["details"])
    payload["features"].update(tenure=0)                                   # tenure 0 -> allowed, passed on as None
    assert client.post(URL, json=payload).status_code == 200
    assert adapter.calls[-1][1]["customer"]["TotalCharges"] is None


def test_total_charges_key_may_not_be_omitted_even_for_new_customers(client, payload):
    payload["features"].update(tenure=0)
    del payload["features"]["TotalCharges"]
    assert_error(client.post(URL, json=payload), 422, "INVALID_INPUT")


@pytest.mark.parametrize("cid", ["", "x" * 65, 123])
def test_customer_id_constraints(client, payload, cid):
    payload["customer_id"] = cid
    assert_error(client.post(URL, json=payload), 422, "INVALID_INPUT")


def test_submitted_values_are_never_echoed_in_validation_errors(client, payload):
    payload["features"]["Contract"] = "TOPSECRET-VALUE-123"
    r = client.post(URL, json=payload)
    assert_error(r, 422, "INVALID_INPUT")
    assert "TOPSECRET-VALUE-123" not in r.text
