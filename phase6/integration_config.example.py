"""EXAMPLE: plug your own Phase 1-5 wiring into the API WITHOUT editing routes, services or schemas.

You only need this file if your project's function names / layout differ from the defaults wired in
``app/services/adapters/phase15_adapter.py::default_bindings()``. In the layout delivered with Phase 1-5 you do NOT.

Usage
-----
1. Copy this file next to your code, e.g. ``my_integration.py`` (any importable module on the Python path).
2. Edit ``build_adapter`` below.
3. Point the API at it:   PowerShell:  $env:TRICHURN_ADAPTER_FACTORY = "my_integration:build_adapter"
4. Start the API. ``GET /api/v1/readiness`` must report ``ready: true``.

The factory receives ``Settings`` and must return an object implementing ``Phase15Port`` (see
``app/services/adapters/interface.py``). If it cannot be imported or does not return a ``Phase15Port`` the API fails
CLOSED (503 INTEGRATION_NOT_CONFIGURED): it never falls back to a fake.
"""
from __future__ import annotations

import dataclasses

from app.core.config import Settings
from app.services.adapters.interface import Phase15Port
from app.services.adapters.phase15_adapter import Phase15Adapter, Phase15Bindings, default_bindings


def my_bindings() -> Phase15Bindings:
    """>>> CONNECT YOUR FUNCTIONS HERE <<<  Start from the defaults and replace only what differs in your project."""
    base = default_bindings()
    return dataclasses.replace(
        base,
        # Each field is a plain callable; replace the ones that differ in your project, for example:
        # load_business_config=lambda: my_package.load_my_business_config(),
        # assign_segment=my_package.assign_segment_for_one_customer,   # (verified_seg, frame) -> (id, name, distance)
    )


def build_adapter(settings: Settings) -> Phase15Port:
    # The bindings are resolved lazily (on first use), so importing this module never imports the ml package.
    return Phase15Adapter(settings, bindings=my_bindings)
