"""The documented example integration file must stay importable and produce a real (non-fake) Phase15Port."""
from __future__ import annotations

import importlib.util
import sys
from pathlib import Path

import pytest

from app.core.config import Settings
from app.main import create_app
from app.services.adapters.factory import build_adapter
from app.services.adapters.interface import Phase15Port
from app.services.adapters.phase15_adapter import Phase15Adapter

EXAMPLE = Path(__file__).resolve().parents[2] / "phase6" / "integration_config.example.py"


@pytest.fixture
def example_module(monkeypatch):
    spec = importlib.util.spec_from_file_location("integration_config_example", EXAMPLE)
    module = importlib.util.module_from_spec(spec)
    monkeypatch.setitem(sys.modules, "integration_config_example", module)
    spec.loader.exec_module(module)
    return module


def test_example_builds_the_real_adapter_not_a_fake(example_module, tmp_path):
    adapter = example_module.build_adapter(Settings(environment="production", project_root=tmp_path))
    assert isinstance(adapter, Phase15Port) and isinstance(adapter, Phase15Adapter)
    assert adapter.is_test_double is False


def test_example_works_through_the_adapter_factory_setting(example_module, tmp_path):
    settings = Settings(environment="production", project_root=tmp_path,
                        adapter_factory="integration_config_example:build_adapter")
    assert isinstance(build_adapter(settings), Phase15Adapter)
    assert create_app(settings=settings).state.services.adapter.is_test_double is False


def test_example_request_file_is_a_valid_request_and_matches_the_openapi_example():
    import json

    from app.schemas.common import CustomerRequest
    body = json.loads((EXAMPLE.parent / "example_request.json").read_text(encoding="utf-8"))
    CustomerRequest.model_validate(body)                                   # strict validation passes
    assert body == CustomerRequest.model_config["json_schema_extra"]["example"]
