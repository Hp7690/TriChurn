"""Fixtures for the Phase 13 API tests.

Everything here is TEST-ONLY synthetic data written to a temporary project root. It is built to exercise validation
and formulas and is never shipped or served by the application. These tests deliberately do not import the host
project's ``tests.support`` so they run in any checkout that has ``app`` and ``trichurn_experience``.
"""

from __future__ import annotations

import copy
from datetime import UTC, datetime
from pathlib import Path

import pytest
import yaml
from fastapi import FastAPI
from fastapi.testclient import TestClient

from app.api.routes.experience import register_experience
from app.core.config import Settings
from app.core.errors import install_error_handlers

NOW = datetime(2026, 11, 11, 12, 0, tzinfo=UTC)
PREFIX = "/api/v1/experience"

CUSTOMERS = (
    "customerID,tenure,Contract,MonthlyCharges,TotalCharges,Churn\n"
    "C001,1,Month-to-month,50,50,Yes\nC002,3,Month-to-month,60,180,No\nC003,8,One year,70,560,No\n"
    "C004,15,One year,80,1200,Yes\nC005,30,Two year,90,2700,No\nC006,60,Two year,100,6000,No\n"
)

BASE_CONFIG = {
    "lifecycle": {"min_group_size_for_rate": 1},
    "surveys": {"min_responses": 3},
    "complaints": {"min_records": 2},
    "journey": {"min_events": 2},
}

FEEDBACK_CSV = (
    "feedback_id,customer_id,feedback_text,submitted_at,channel,sentiment_label\n"
    "f1,C001,Great service,2026-10-01,email,positive\nf2,C002,Slow support,2026-10-02,chat,negative\n"
    "f3,C003,It is fine,2026-10-03,app,\n"
)
TICKETS_CSV = (
    "ticket_id,customer_id,category,severity,status,created_at,resolved_at,sla_due_at\n"
    "T1,C001,billing,high,resolved,2026-10-01T00:00:00Z,2026-10-01T10:00:00Z,2026-10-02T00:00:00Z\n"
    "T2,C002,network,low,open,2026-10-02T00:00:00Z,,2026-10-03T00:00:00Z\n"
    "T3,C003,billing,critical,closed,2026-10-03T00:00:00Z,2026-10-05T00:00:00Z,2026-10-04T00:00:00Z\n"
)
NPS_CSV = (
    "response_id,customer_id,score,survey_date\nn1,C001,10,2026-10-01\nn2,C002,9,2026-10-02\n"
    "n3,C003,6,2026-10-03\nn4,C004,8,2026-11-01\n"
)
CSAT_CSV = (
    "response_id,customer_id,score,survey_date\ns1,C001,5,2026-10-01\ns2,C002,4,2026-10-02\ns3,C003,2,2026-10-03\n"
)
EVENTS_CSV = (
    "customer_id,event_type,event_timestamp,channel\nC001,signup,2026-10-01T00:00:00Z,web\n"
    "C001,login,2026-10-02T00:00:00Z,app\nC002,signup,2026-10-01T00:00:00Z,web\n"
)


class Env:
    def __init__(self, root: Path, client: TestClient, app: FastAPI):
        self.root, self.client, self.app = root, client, app

    def get(self, path, **kw):
        return self.client.get(PREFIX + path, **kw)

    def post(self, path, **kw):
        return self.client.post(PREFIX + path, **kw)

    @property
    def data_dir(self) -> Path:
        return self.root / "data" / "experience"

    def tree(self) -> dict[str, int]:
        return {str(p.relative_to(self.root)): p.stat().st_size for p in sorted(self.root.rglob("*")) if p.is_file()}


@pytest.fixture
def make_env(tmp_path):
    def build(
        config: dict | None = None,
        *,
        datasets: dict[str, str] | None = None,
        customers: str | None = CUSTOMERS,
        raw_config: str | None = None,
        **service_kwargs,
    ) -> Env:
        root = tmp_path / "project"
        (root / "configs").mkdir(parents=True, exist_ok=True)
        (root / "data" / "experience").mkdir(parents=True, exist_ok=True)
        if customers is not None:
            (root / "customers.csv").write_text(customers, encoding="utf-8")
        cfg = copy.deepcopy(BASE_CONFIG)
        for key, value in (config or {}).items():
            cfg[key] = (
                {**cfg.get(key, {}), **value} if isinstance(value, dict) and isinstance(cfg.get(key), dict) else value
            )
        mapping = {}
        for kind, spec in (datasets or {}).items():
            filename, content = spec
            if content is not None:
                (root / "data" / "experience" / filename).parent.mkdir(parents=True, exist_ok=True)
                (root / "data" / "experience" / filename).write_text(content, encoding="utf-8")
            mapping[kind] = filename
        if mapping:
            cfg["datasets"] = mapping
        (root / "configs" / "experience.yaml").write_text(
            raw_config if raw_config is not None else yaml.safe_dump(cfg), encoding="utf-8"
        )
        settings = Settings(environment="test", project_root=root, dataset_csv_path="customers.csv")
        app = FastAPI()
        app.state.settings = settings
        install_error_handlers(app)
        register_experience(app, settings, clock=lambda: NOW, **service_kwargs)
        return Env(root, TestClient(app, raise_server_exceptions=False), app)

    return build


def assert_error(response, status: int, code: str) -> dict:
    assert response.status_code == status, response.text
    body = response.json()
    assert set(body) == {"error"} and body["error"]["code"] == code and body["error"]["message"]
    assert "Traceback" not in response.text
    return body["error"]
