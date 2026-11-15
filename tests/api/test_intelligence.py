"""POST /api/v1/customer-intelligence: orchestration, consistency and all-or-nothing behaviour."""
from __future__ import annotations

import pytest

from tests.api.conftest import assert_error
from tests.support.fake_adapter import FakeAdapter

URL = "/api/v1/customer-intelligence"


def test_combined_response(client, payload):
    r = client.post(URL, json=payload)
    assert r.status_code == 200
    b = r.json()
    assert set(b) == {"customer_id", "prediction", "explanation", "business", "segment", "notes"}
    assert b["customer_id"] == "EXAMPLE-0001"
    p, e, biz, s = b["prediction"], b["explanation"], b["business"], b["segment"]
    assert p["churn_probability"] == e["churn_probability"] == biz["churn_probability"]
    assert p["risk_band"] == biz["risk_band"] and p["predicted_churn"] == e["predicted_churn"]
    assert s["segment_name"] and len(b["notes"]) == 3


def test_steps_run_in_order_exactly_once_and_results_are_handed_forward(client, adapter, payload):
    client.post(URL, json=payload)
    assert [op for op, _ in adapter.calls] == ["predict", "explain", "business", "segment"]
    business_args = dict(adapter.calls)["business"]
    predicted = client.post("/api/v1/predict", json=payload).json()["churn_probability"]
    assert business_args["churn_probability"] == predicted               # the SAME probability, not a recomputation
    assert business_args["explanation"] is not None                      # SHAP result is forwarded to the explainer


def test_business_text_uses_the_forwarded_shap_drivers(client, payload):
    combined = client.post(URL, json=payload).json()["business"]["explanation"]["model_explanation"]
    standalone = client.post("/api/v1/business", json=payload).json()["explanation"]["model_explanation"]
    assert "drivers" in combined and "drivers" not in standalone          # /business alone has no SHAP input


@pytest.mark.parametrize("missing", ["phase2_model", "explainability", "business_engine", "segmentation"])
def test_any_unavailable_capability_fails_the_whole_request(make_client, payload, missing):
    c = make_client(adapter := FakeAdapter(unavailable={missing}))
    assert_error(c.post(URL, json=payload), 503, "CAPABILITY_UNAVAILABLE")
    assert len(adapter.calls) >= 1                                       # no partial / fabricated result is returned


def test_later_steps_are_not_run_after_a_failure(make_client, payload):
    adapter = FakeAdapter(unavailable={"explainability"})
    make_client(adapter).post(URL, json=payload)
    assert [op for op, _ in adapter.calls] == ["predict", "explain"]


def test_inconsistent_model_outputs_are_withheld(make_client, payload):
    c = make_client(FakeAdapter(explain_probability_offset=0.01))        # explainer disagrees with the model
    err = assert_error(c.post(URL, json=payload), 500, "INCONSISTENT_RESULTS")
    assert "withheld" in err["message"]


def test_validation_happens_before_any_computation(client, adapter, payload):
    del payload["features"]["Contract"]
    assert_error(client.post(URL, json=payload), 422, "INVALID_INPUT")
    assert adapter.calls == []
