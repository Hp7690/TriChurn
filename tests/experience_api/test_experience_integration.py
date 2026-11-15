"""Host-integration checks. These run only AFTER scripts/integrate_phase13.py has patched app/main.py; before that
they are skipped (the overlay itself must not require the host to be patched).

They prove the two guarantees that matter at the seam: every pre-existing endpoint is still mounted, and the
experience endpoints answer from the real project configuration (no mock data, no fake adapter)."""

from __future__ import annotations

from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]
MAIN = ROOT / "app" / "main.py"

pytestmark = pytest.mark.skipif(
    not MAIN.is_file() or "register_experience" not in MAIN.read_text(encoding="utf-8"),
    reason="Phase 13 is not integrated into app/main.py yet",
)

# The 8 endpoints present in the Phase 6 snapshot. A project with Phase 9 has more; all of these must still exist.
EXISTING = {
    "/api/v1/business",
    "/api/v1/customer-intelligence",
    "/api/v1/explain",
    "/api/v1/health",
    "/api/v1/liveness",
    "/api/v1/predict",
    "/api/v1/readiness",
    "/api/v1/segment",
}


@pytest.fixture(scope="module")
def client():
    from fastapi.testclient import TestClient

    from app.core.config import Settings
    from app.main import create_app
    from app.services.adapters.unavailable import UnavailableAdapter

    app = create_app(
        adapter=UnavailableAdapter("phase13-integration-test"), settings=Settings(environment="test", project_root=ROOT)
    )
    return TestClient(app, raise_server_exceptions=False), app


def test_all_existing_endpoints_are_still_mounted(client):
    _, app = client
    assert EXISTING <= set(app.openapi()["paths"])


def test_experience_endpoints_are_mounted(client):
    _, app = client
    paths = set(app.openapi()["paths"])
    for suffix in (
        "availability",
        "lifecycle",
        "validate-feedback",
        "validate-tickets",
        "validate-survey",
        "validate-events",
        "data-quality",
        "sentiment/status",
        "complaints/status",
        "nps/status",
        "csat/status",
        "journey/status",
    ):
        assert f"/api/v1/experience/{suffix}" in paths


def test_existing_health_endpoint_is_unaffected(client):
    c, _ = client
    assert c.get("/api/v1/liveness").status_code == 200


def test_availability_answers_from_real_configuration(client):
    c, _ = client
    body = c.get("/api/v1/experience/availability").json()
    modules = {m["module"]: m for m in body["modules"]}
    assert set(modules) == {"lifecycle", "feedback", "sentiment", "complaints", "nps", "csat", "journey"}
    # With no experience datasets configured, none of the data-dependent modules may report figures.
    for key in ("feedback", "sentiment", "complaints", "nps", "csat", "journey"):
        if not modules[key]["dataset_configured"]:
            assert modules[key]["status"] == "BLOCKED_BY_MISSING_DATA" and modules[key]["metrics"] is None
