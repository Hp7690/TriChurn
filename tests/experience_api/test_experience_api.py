"""Phase 13 API tests: availability, lifecycle, validation endpoints, module status, errors, limits, no persistence."""

from __future__ import annotations

import json

import pytest

from tests.experience_api.conftest import (
    CSAT_CSV,
    EVENTS_CSV,
    FEEDBACK_CSV,
    NPS_CSV,
    TICKETS_CSV,
    assert_error,
)
from trichurn_experience.sentiment import SentimentModelMetadata, SentimentPrediction

ALL = {
    "feedback": ("feedback.csv", FEEDBACK_CSV),
    "tickets": ("tickets.csv", TICKETS_CSV),
    "nps": ("nps.csv", NPS_CSV),
    "csat": ("csat.csv", CSAT_CSV),
    "events": ("events.csv", EVENTS_CSV),
}
DATA_MODULES = ("complaints", "nps", "csat", "journey")
VALID_UPLOADS = {"validate-feedback": FEEDBACK_CSV, "validate-tickets": TICKETS_CSV, "validate-events": EVENTS_CSV}


def csv_body(content, **extra):
    return {"format": "csv", "content": content, **extra}


# ------------------------------------------------------------------------------------------------ availability
def test_default_availability_blocks_every_data_module_and_runs_only_lifecycle(make_env):
    body = make_env().get("/availability").json()
    status = {m["module"]: m["status"] for m in body["modules"]}
    assert status == {
        "lifecycle": "AVAILABLE",
        "feedback": "BLOCKED_BY_MISSING_DATA",
        "sentiment": "BLOCKED_BY_MISSING_DATA",
        "complaints": "BLOCKED_BY_MISSING_DATA",
        "nps": "BLOCKED_BY_MISSING_DATA",
        "csat": "BLOCKED_BY_MISSING_DATA",
        "journey": "BLOCKED_BY_MISSING_DATA",
    }
    assert body["summary"]["AVAILABLE"] == 1 and body["summary"]["BLOCKED_BY_MISSING_DATA"] == 6
    assert body["enabled"] is True and body["config_error"] is None and body["notices"]
    for m in body["modules"]:
        if m["module"] != "lifecycle":
            assert m["metrics"] is None and m["dataset_configured"] is False
            assert m["requirements"]["needs"], "every blocked module explains what data activates it"


def test_availability_lifecycle_summary_and_data_quality_come_from_the_file(make_env):
    body = make_env().get("/availability").json()
    assert body["lifecycle_summary"]["customers_analysed"] == 6 and body["lifecycle_summary"]["is_event_based"] is False
    q = body["data_quality"]["customer_dataset"]
    assert q["rows"] == 6 and q["duplicate_customer_ids"] == 0 and q["missing_total_charges"] == 0
    assert all(v is None for v in body["data_quality"]["datasets"].values())


def test_customer_data_quality_reports_real_defects(make_env):
    bad = (
        "customerID,tenure,Contract,MonthlyCharges,TotalCharges,Churn\n"
        "C1,1,Month-to-month,50, ,Yes\nC1,abc,One year,60,100,No\nC3,-2,One year,70,100,\n"
    )
    q = make_env(customers=bad).get("/availability").json()["data_quality"]["customer_dataset"]
    assert q["duplicate_customer_ids"] == 1 and q["missing_tenure_or_invalid"] == 2
    assert q["missing_total_charges"] == 1 and q["missing_churn_label"] == 1


def test_availability_without_customer_file_is_blocked_not_an_error(make_env):
    body = make_env(customers=None).get("/availability").json()
    assert {m["module"]: m["status"] for m in body["modules"]}["lifecycle"] == "BLOCKED_BY_MISSING_DATA"
    assert body["lifecycle_summary"] is None and body["data_quality"]["customer_dataset"] is None


# ------------------------------------------------------------------------------------------------ lifecycle
def test_lifecycle_endpoint_returns_proxy_labelled_groups(make_env):
    body = make_env().get("/lifecycle").json()
    assert body["label"] == "TENURE_PROXY" and body["is_event_based"] is False and body["status"] == "AVAILABLE"
    assert [g["customers"] for g in body["groups"]] == [2, 1, 1, 1, 1]
    assert body["groups"][0]["churn"]["churned"] == 1 and body["overall"]["churn_rate_pct"] == pytest.approx(33.33)
    assert body["risk_distribution"]["status"] == "BLOCKED_BY_MISSING_DATA"
    assert (
        body["source"] == "Customer dataset: customers.csv" and "\\" not in body["source"] and "/" not in body["source"]
    )
    assert "not an event-based customer journey" in body["methodology"]


def test_lifecycle_uses_configured_thresholds(make_env):
    cfg = {
        "lifecycle": {
            "groups": [
                {"name": "Young", "min_months": 0, "max_months": 10},
                {"name": "Old", "min_months": 10, "max_months": None},
            ]
        }
    }
    body = make_env(cfg).get("/lifecycle").json()
    assert [(g["name"], g["customers"]) for g in body["groups"]] == [("Young", 3), ("Old", 3)]


def test_lifecycle_risk_from_injected_provider_and_provider_failure_degrades(make_env):
    env = make_env(probability_provider=lambda: {"C001": 0.9, "C002": 0.1})
    risk = env.get("/lifecycle").json()["risk_distribution"]
    assert risk["status"] == "AVAILABLE" and risk["bands"] == {"LOW": 1, "MEDIUM": 0, "HIGH": 1}
    assert risk["missing_probability"] == 4

    def boom():
        raise RuntimeError("internal detail /secret/path")

    broken = make_env(probability_provider=boom).get("/lifecycle")
    assert broken.status_code == 200 and "secret" not in broken.text
    assert broken.json()["risk_distribution"]["status"] == "BLOCKED_BY_MISSING_DATA"


def test_lifecycle_dataset_without_tenure_fails_validation(make_env):
    body = make_env(customers="customerID,Churn\nC1,No\n").get("/lifecycle").json()
    assert body["status"] == "VALIDATION_FAILED" and body["groups"] == []


def test_lifecycle_can_be_disabled(make_env):
    body = make_env({"lifecycle": {"enabled": False}}).get("/lifecycle").json()
    assert body["status"] == "DISABLED" and body["groups"] == []


# ------------------------------------------------------------------------------------------------ validation endpoints
@pytest.mark.parametrize("path,content", VALID_UPLOADS.items())
def test_validate_endpoints_accept_valid_csv(make_env, path, content):
    body = make_env().post(f"/{path}", json=csv_body(content)).json()
    assert (
        body["report"]["valid"] is True and body["report"]["persisted"] is False and body["report"]["rows_total"] == 3
    )


@pytest.mark.parametrize("survey_type,content", [("nps", NPS_CSV), ("csat", CSAT_CSV)])
def test_validate_survey_for_both_types(make_env, survey_type, content):
    body = make_env().post("/validate-survey", json=csv_body(content, survey_type=survey_type)).json()
    assert body["report"]["valid"] is True and body["report"]["kind"] == survey_type


def test_validate_survey_scale_depends_on_type(make_env):
    content = "response_id,customer_id,score,survey_date\nr1,C001,8,2026-10-01\n"
    env = make_env()
    assert env.post("/validate-survey", json=csv_body(content, survey_type="nps")).json()["report"]["valid"] is True
    csat = env.post("/validate-survey", json=csv_body(content, survey_type="csat")).json()["report"]
    assert csat["valid"] is False and csat["issue_counts"] == {"score_out_of_scale": 1}


def test_validate_json_payload(make_env):
    records = [
        {"customer_id": "C1", "event_type": "login", "event_timestamp": "2026-10-01T00:00:00Z", "channel": "app"}
    ]
    body = make_env().post("/validate-events", json={"format": "json", "content": json.dumps(records)}).json()
    assert body["report"]["valid"] is True and body["report"]["file_format"] == "json"


def test_invalid_upload_returns_report_with_row_level_issues_not_values(make_env):
    content = (
        "feedback_id,customer_id,feedback_text,submitted_at\nf1,bad id!,hello,SECRET-DATE\nf1,C2,hello,2026-10-01\n"
    )
    resp = make_env().post("/validate-feedback", json=csv_body(content))
    rep = resp.json()["report"]
    assert resp.status_code == 200 and rep["valid"] is False
    assert rep["invalid_customer_ids"] == 1 and rep["invalid_timestamps"] == 1 and rep["duplicate_records"] == 1
    assert {i["row"] for i in rep["issues"]} <= {1, 2} and "SECRET-DATE" not in resp.text and "bad id!" not in resp.text


@pytest.mark.parametrize(
    "path", ["validate-feedback", "validate-tickets", "validate-events", "validate-survey", "data-quality"]
)
def test_malformed_payloads_use_the_error_envelope(make_env, path):
    env = make_env()
    for payload in (
        {},
        {"format": "csv"},
        {"content": "x"},
        {"format": "xml", "content": "x"},
        {"format": "csv", "content": 5},
        {"format": "csv", "content": "x", "surprise": 1},
    ):
        assert_error(env.post(f"/{path}", json=payload), 422, "INVALID_INPUT")
    assert env.post(f"/{path}", content=b"not json", headers={"content-type": "application/json"}).status_code == 422


def test_survey_type_and_dataset_are_required_and_constrained(make_env):
    env = make_env()
    assert_error(env.post("/validate-survey", json=csv_body("a,b\n1,2\n")), 422, "INVALID_INPUT")
    assert_error(env.post("/validate-survey", json=csv_body("a\n1\n", survey_type="nps2")), 422, "INVALID_INPUT")
    assert_error(env.post("/data-quality", json=csv_body("a\n1\n", dataset="telco")), 422, "INVALID_INPUT")


def test_unparseable_content_is_422_without_echoing_it(make_env):
    env = make_env()
    r = env.post("/validate-events", json={"format": "json", "content": "{not-json SECRET"})
    assert "SECRET" not in r.text
    assert_error(r, 422, "INVALID_INPUT")
    assert_error(env.post("/validate-events", json=csv_body("")), 422, "INVALID_INPUT")
    assert_error(env.post("/validate-events", json=csv_body("a,b\n\x00,1\n")), 422, "INVALID_INPUT")


def test_oversized_content_is_rejected_with_413(make_env):
    env = make_env({"limits": {"max_bytes": 200}})
    big = "customer_id,event_type,event_timestamp,channel\n" + "C1,login,2026-10-01T00:00:00Z,app\n" * 20
    assert_error(env.post("/validate-events", json=csv_body(big)), 413, "INVALID_INPUT")


def test_oversized_request_body_is_rejected_by_the_content_length_guard(make_env):
    env = make_env({"limits": {"max_bytes": 100}})
    resp = env.post(
        "/validate-events",
        content=b'{"format":"csv","content":"' + b"x" * 5000 + b'"}',
        headers={"content-type": "application/json"},
    )
    assert_error(resp, 413, "INVALID_INPUT")


def test_row_and_column_limits_return_413(make_env):
    env = make_env({"limits": {"max_rows": 2, "max_columns": 6}})
    rows = "customer_id,event_type,event_timestamp,channel\n" + "C1,login,2026-10-01T00:00:00Z,app\n" * 3
    assert_error(env.post("/validate-events", json=csv_body(rows)), 413, "INVALID_INPUT")
    wide = ",".join(f"c{i}" for i in range(7)) + "\n" + ",".join("1" for _ in range(7)) + "\n"
    assert_error(env.post("/validate-events", json=csv_body(wide)), 413, "INVALID_INPUT")


def test_data_quality_endpoint(make_env):
    content = (
        "response_id,customer_id,score,survey_date\nr1,C1,9,2026-10-01\nr1,C2,8,2026-10-02\nr3,C3,7,2026-10-03\n"
        "r4,C4,,2026-10-04\n"
    )
    body = make_env().post("/data-quality", json=csv_body(content, dataset="nps")).json()
    assert body["report"]["duplicate_records"] == 1 and body["report"]["missing_value_counts"]["score"] == 1
    q = body["quality"]
    assert q["rows_total"] == 4 and q["valid_row_pct"] == 50.0 and q["duplicate_pct"] == 25.0
    assert q["completeness_pct_by_column"]["score"] == 75.0


def test_validation_uploads_are_never_persisted(make_env):
    env = make_env()
    before = env.tree()
    for path, content in VALID_UPLOADS.items():
        env.post(f"/{path}", json=csv_body(content))
    env.post("/data-quality", json=csv_body(NPS_CSV, dataset="nps"))
    assert env.tree() == before and list(env.data_dir.iterdir()) == []
    assert env.get("/availability").json()["data_quality"]["datasets"]["feedback"] is None


# ------------------------------------------------------------------------------------------------ module status
STATUS_PATHS = ["/sentiment/status", "/complaints/status", "/nps/status", "/csat/status", "/journey/status"]


@pytest.mark.parametrize("path", STATUS_PATHS)
def test_status_endpoints_are_blocked_without_data(make_env, path):
    body = make_env().get(path).json()
    assert body["status"] == "BLOCKED_BY_MISSING_DATA" and body["metrics"] is None and body["reason"]
    assert body["dataset_configured"] is False and body["requirements"]["needs"]


def test_sentiment_blocked_reason_mentions_missing_feedback_text(make_env):
    assert "no feedback text" in make_env().get("/sentiment/status").json()["reason"]


def test_configured_datasets_activate_modules_with_real_calculations(make_env):
    env = make_env(datasets=ALL)
    cmp = env.get("/complaints/status").json()
    assert cmp["status"] == "AVAILABLE" and cmp["metrics"]["tickets_total"] == 3
    assert cmp["metrics"]["sla"]["met"] == 1 and cmp["metrics"]["sla"]["breached"] == 2
    nps = env.get("/nps/status").json()["metrics"]
    assert (nps["promoters"], nps["passives"], nps["detractors"], nps["value"]) == (2, 1, 1, 25.0)
    csat = env.get("/csat/status").json()["metrics"]
    assert csat["satisfied"] == 2 and csat["value"] == pytest.approx(66.67)
    jr = env.get("/journey/status").json()["metrics"]
    assert jr["events_total"] == 3 and jr["customers"] == 2
    fb = env.get("/availability").json()
    status = {m["module"]: m for m in fb["modules"]}
    assert status["feedback"]["status"] == "AVAILABLE" and status["feedback"]["metrics"]["human_label_counts"] == {
        "positive": 1,
        "negative": 1,
    }
    assert status["sentiment"]["status"] == "PARTIALLY_AVAILABLE"  # data exists, no model registered
    assert fb["summary"]["BLOCKED_BY_MISSING_DATA"] == 0 and fb["data_quality"]["datasets"]["nps"]["rows_total"] == 4


def test_survey_period_parameters(make_env):
    env = make_env(datasets=ALL)
    metrics = env.get("/nps/status", params={"period_start": "2026-10-01", "period_end": "2026-10-31"}).json()[
        "metrics"
    ]
    assert (
        metrics["valid_responses"] == 3 and metrics["out_of_period"] == 1 and metrics["value"] == pytest.approx(33.33)
    )
    empty = env.get("/nps/status", params={"period_start": "2027-01-01"}).json()
    assert empty["status"] == "BLOCKED_BY_MISSING_DATA" and empty["metrics"] is None
    assert_error(
        env.get("/nps/status", params={"period_start": "2026-12-01", "period_end": "2026-01-01"}), 422, "INVALID_INPUT"
    )
    assert_error(env.get("/csat/status", params={"period_end": "nope"}), 422, "INVALID_INPUT")


def test_invalid_configured_dataset_is_validation_failed_and_computes_nothing(make_env):
    bad = "response_id,customer_id,score,survey_date\nn1,C1,99,2026-10-01\n"
    body = make_env(datasets={"nps": ("nps.csv", bad)}).get("/nps/status").json()
    assert body["status"] == "VALIDATION_FAILED" and body["metrics"] is None
    assert body["validation"]["valid"] is False and body["validation"]["error_count"] == 1


@pytest.mark.parametrize("name", ["../outside.csv", "/etc/passwd.csv", "a/../../b.csv", "data.exe", "C:\\x.csv"])
def test_unsafe_configured_paths_are_rejected(make_env, name):
    body = make_env(datasets={"nps": (name, None)}).get("/nps/status").json()
    assert body["status"] == "VALIDATION_FAILED" and body["metrics"] is None
    assert "\\" not in body["reason"] and str(make_env.__module__) not in body["reason"]


def test_configured_file_that_is_missing_is_blocked(make_env):
    body = make_env(datasets={"nps": ("absent.csv", None)}).get("/nps/status").json()
    assert body["status"] == "BLOCKED_BY_MISSING_DATA" and body["dataset_configured"] is True


def test_oversized_configured_file_is_validation_failed(make_env):
    env = make_env({"limits": {"max_bytes": 50}}, datasets={"nps": ("nps.csv", NPS_CSV)})
    assert env.get("/nps/status").json()["status"] == "VALIDATION_FAILED"


def test_json_dataset_files_are_supported(make_env):
    records = [
        {"response_id": f"r{i}", "customer_id": "C1", "score": s, "survey_date": "2026-10-01"}
        for i, s in enumerate([10, 3])
    ]
    env = make_env(datasets={"nps": ("nps.json", json.dumps(records))})
    assert env.get("/nps/status").json()["metrics"]["value"] == 0.0


def test_dataset_changes_are_picked_up_without_restart(make_env):
    env = make_env(datasets={"nps": ("nps.csv", NPS_CSV)})
    assert env.get("/nps/status").json()["metrics"]["valid_responses"] == 4
    (env.data_dir / "nps.csv").write_text(NPS_CSV + "n5,C5,0,2026-10-05\n", encoding="utf-8")
    assert env.get("/nps/status").json()["metrics"]["valid_responses"] == 5


# ------------------------------------------------------------------------------------------------ sentiment model hook
class _Model:
    metadata = SentimentModelMetadata("test-only", "0", "2026-01-01T00:00:00Z", ("positive", "negative"), "c" * 64, 5)

    def predict(self, ids, texts):
        return [SentimentPrediction(i, "positive", 0.9) for i in ids]


def test_sentiment_becomes_available_only_with_data_and_a_registered_model(make_env):
    env = make_env(datasets={"feedback": ("feedback.csv", FEEDBACK_CSV)}, sentiment_model=_Model())
    body = env.get("/sentiment/status").json()
    assert body["status"] == "AVAILABLE" and body["metrics"]["model"]["name"] == "test-only"
    assert make_env(sentiment_model=_Model()).get("/sentiment/status").json()["status"] == "BLOCKED_BY_MISSING_DATA"


# ------------------------------------------------------------------------------------------------ config states
def test_disabled_configuration(make_env):
    env = make_env({"enabled": False})
    body = env.get("/availability").json()
    assert body["enabled"] is False and all(m["status"] == "DISABLED" for m in body["modules"])
    assert_error(env.post("/validate-feedback", json=csv_body(FEEDBACK_CSV)), 503, "CAPABILITY_UNAVAILABLE")


def test_invalid_configuration_never_breaks_the_api(make_env):
    env = make_env(raw_config="limits: {max_bytes: -5}\n")
    body = env.get("/availability")
    assert body.status_code == 200
    data = body.json()
    assert data["config_error"] and all(m["status"] == "VALIDATION_FAILED" for m in data["modules"])
    assert env.get("/lifecycle").json()["status"] == "VALIDATION_FAILED"
    assert_error(env.post("/validate-feedback", json=csv_body(FEEDBACK_CSV)), 503, "CAPABILITY_UNAVAILABLE")


def test_missing_config_file_degrades_to_validation_failed(make_env, tmp_path):
    env = make_env()
    (env.root / "configs" / "experience.yaml").unlink()
    from fastapi import FastAPI
    from fastapi.testclient import TestClient

    from app.api.routes.experience import register_experience
    from app.core.errors import install_error_handlers

    app = FastAPI()
    install_error_handlers(app)
    register_experience(app, env.app.state.settings)
    assert TestClient(app).get("/api/v1/experience/availability").json()["config_error"]


# ------------------------------------------------------------------------------------------------ routing and errors
def test_unknown_routes_and_methods_use_the_envelope(make_env):
    env = make_env()
    assert_error(env.get("/nope"), 404, "NOT_FOUND")
    assert_error(env.client.get("/api/v1/experience/validate-feedback"), 405, "METHOD_NOT_ALLOWED")
    assert_error(env.client.post("/api/v1/experience/availability"), 405, "METHOD_NOT_ALLOWED")


def test_service_missing_returns_capability_unavailable(make_env):
    env = make_env()
    del env.app.state.experience_service
    assert_error(env.get("/availability"), 503, "CAPABILITY_UNAVAILABLE")


def test_openapi_lists_every_experience_endpoint(make_env):
    paths = set(make_env().app.openapi()["paths"])
    expected = {
        "/availability",
        "/lifecycle",
        "/validate-feedback",
        "/validate-tickets",
        "/validate-survey",
        "/validate-events",
        "/sentiment/status",
        "/complaints/status",
        "/nps/status",
        "/csat/status",
        "/journey/status",
        "/data-quality",
    }
    assert {f"/api/v1/experience{p}" for p in expected} <= paths


def test_responses_never_contain_server_paths(make_env):
    env = make_env(datasets=ALL)
    root = str(env.root)
    for path in ["/availability", "/lifecycle", *STATUS_PATHS]:
        assert root not in env.get(path).text
