"""Shared service plumbing: every adapter call is guarded so unexpected errors become opaque 500s."""
from __future__ import annotations

from collections.abc import Callable
from typing import Any, TypeVar

from app.core.errors import ApiError, internal_error
from app.schemas.common import CustomerRequest
from app.services.adapters.interface import Phase15Port

T = TypeVar("T")


def customer_payload(request: CustomerRequest) -> dict[str, Any]:
    """Exactly the validated features: no defaults added, nothing removed."""
    return request.features.model_dump()


class BaseService:
    def __init__(self, adapter: Phase15Port):
        self._adapter = adapter

    @staticmethod
    def guard(fn: Callable[..., T], *args: Any, **kwargs: Any) -> T:
        try:
            return fn(*args, **kwargs)
        except ApiError:
            raise
        except Exception as exc:
            raise internal_error(exc) from exc
