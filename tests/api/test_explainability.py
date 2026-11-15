from __future__ import annotations

from tests.api.conftest import assert_error

URL = "/api/v1/explain"


def test_explain_response(client, payload):
    r = client.post(URL, json=payload)
    assert r.status_code == 200
    b = r.json()
    assert set(b) == {"customer_id", "churn_probability", "predicted_churn", "decision_threshold", "output_space",
                      "base_value", "model_log_odds", "reconstruction_error", "features", "interpretation",
                      "model_version"}
    assert b["output_space"] == "log_odds" and b["reconstruction_error"] <= 1e-6
    shap = [abs(f["shap_value"]) for f in b["features"]]
    assert shap == sorted(shap, reverse=True)                              # Phase 3 ordering is preserved
    assert {f["direction"] for f in b["features"]} <= {"increases_churn", "decreases_churn", "neutral"}
    assert set(b["features"][0]) == {"source_feature", "raw_value", "shap_value", "direction", "is_engineered"}
    assert "not causes" in b["interpretation"]


def test_top_n_truncates_without_reordering(client, payload):
    full = client.post(URL, json=payload).json()["features"]
    payload["top_n"] = 2
    assert client.post(URL, json=payload).json()["features"] == full[:2]


def test_top_n_bounds(client, payload):
    for bad in (0, -1, 101, "3"):
        payload["top_n"] = bad
        assert_error(client.post(URL, json=payload), 422, "INVALID_INPUT")


def test_explain_requires_the_same_strict_features(client, adapter, payload):
    del payload["features"]["tenure"]
    assert_error(client.post(URL, json=payload), 422, "INVALID_INPUT")
    assert adapter.calls == []


def test_explainability_unavailable_is_a_clean_503(make_client, payload):
    c = make_client(__import__("tests.support.fake_adapter", fromlist=["FakeAdapter"]).FakeAdapter(
        unavailable={"explainability"}))
    err = assert_error(c.post(URL, json=payload), 503, "CAPABILITY_UNAVAILABLE")
    assert "explainability" in err["message"]
