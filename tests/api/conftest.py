"""Fixtures for the API tests. They use the TEST-ONLY fake adapter; the real Phase 1-5 wiring is tested in
tests/api/test_real_integration.py (which needs the existing project)."""
from __future__ import annotations

import copy
from collections.abc import Callable
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from app.core.config import Settings
from app.main import create_app
from app.schemas.common import CustomerRequest
from tests.support.fake_adapter import FakeAdapter

EXAMPLE = CustomerRequest.model_config["json_schema_extra"]["example"]      # type: ignore[index]
FEATURE_NAMES = sorted(EXAMPLE["features"])


@pytest.fixture
def settings(tmp_path: Path) -> Settings:
    return Settings(environment="test", project_root=tmp_path)


@pytest.fixture
def payload() -> dict:
    return copy.deepcopy(EXAMPLE)


@pytest.fixture
def adapter() -> FakeAdapter:
    return FakeAdapter()


@pytest.fixture
def client(adapter: FakeAdapter, settings: Settings) -> TestClient:
    return TestClient(create_app(adapter=adapter, settings=settings))


@pytest.fixture
def make_client(settings: Settings) -> Callable[..., TestClient]:
    def build(adapter: FakeAdapter, **kwargs) -> TestClient:
        return TestClient(create_app(adapter=adapter, settings=settings), **kwargs)
    return build


def assert_error(response, status: int, code: str) -> dict:
    """Every error uses the envelope and never leaks internals."""
    assert response.status_code == status, response.text
    body = response.json()
    assert set(body) == {"error"} and body["error"]["code"] == code and body["error"]["message"]
    text = response.text
    for forbidden in ("Traceback", "File \"", "C:\\", "/home/", "site-packages", ".joblib", "venv"):
        assert forbidden not in text, f"leaked {forbidden!r}: {text}"
    return body["error"]
