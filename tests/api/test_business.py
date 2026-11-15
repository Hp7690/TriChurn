from __future__ import annotations

from tests.api.conftest import assert_error
from tests.support.fake_adapter import FakeAdapter

URL = "/api/v1/business"


def test_business_response(client, payload):
    r = client.post(URL, json=payload)
    assert r.status_code == 200
    b = r.json()
    for key in ("churn_probability", "risk_band", "currency", "clv", "value_at_risk", "intervention_decision",
                "recommended_action_id", "recommended_action", "action_cost", "action_success_rate",
                "expected_benefit", "expected_cost", "expected_net_benefit", "decision_reasons",
                "decision_reason_messages", "action_evaluations", "explanation", "notice"):
        assert key in b, key
    assert b["intervention_decision"] in {"INTERVENE", "DO_NOT_INTERVENE"}
    assert set(b["explanation"]) == {"model_explanation", "business_decision", "disclaimer"}
    assert {"action_id", "name", "cost", "success_rate", "eligible", "expected_net_benefit"} <= set(
        b["action_evaluations"][0])


def test_business_leaves_the_probability_to_the_locked_model(client, adapter, payload):
    client.post(URL, json=payload)
    (op, args), = adapter.calls
    assert op == "business" and args["churn_probability"] is None and args["explanation"] is None


def test_clients_cannot_supply_the_churn_probability_or_a_clv(client, adapter, payload):
    for extra in ({"churn_probability": 0.9}, {"clv": 5000}, {"action_success_rate": 1.0}):
        assert_error(client.post(URL, json={**payload, **extra}), 422, "INVALID_INPUT")
    assert adapter.calls == []


def test_business_unavailable_is_a_clean_503(make_client, payload):
    c = make_client(FakeAdapter(unavailable={"business_engine"}))
    assert_error(c.post(URL, json=payload), 503, "CAPABILITY_UNAVAILABLE")
