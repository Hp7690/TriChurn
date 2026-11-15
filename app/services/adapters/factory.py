"""Chooses the adapter at start-up. Production NEVER falls back to a fake: failures give ``UnavailableAdapter``."""
from __future__ import annotations

import importlib
import logging

from app.core.config import Settings
from app.services.adapters.interface import Phase15Port
from app.services.adapters.phase15_adapter import Phase15Adapter
from app.services.adapters.unavailable import UnavailableAdapter

logger = logging.getLogger("trichurn.api.adapter")


def build_adapter(settings: Settings) -> Phase15Port:
    """Default: the real ``Phase15Adapter``. ``TRICHURN_ADAPTER_FACTORY="package.module:callable"`` plugs in your own
    ``Phase15Port`` (the callable receives ``Settings``)."""
    if not settings.adapter_factory:
        return Phase15Adapter(settings)
    try:
        module_name, _, attr = settings.adapter_factory.partition(":")
        if not module_name or not attr:
            raise ValueError("expected 'package.module:callable'")
        adapter = getattr(importlib.import_module(module_name), attr)(settings)
        if not isinstance(adapter, Phase15Port):
            raise TypeError("factory did not return a Phase15Port")
    except Exception as exc:  # noqa: BLE001 - fail closed, details only in the server log
        logger.error("Adapter factory could not be used (%s)", type(exc).__name__, exc_info=exc)
        return UnavailableAdapter("adapter_factory_failed")
    return adapter
