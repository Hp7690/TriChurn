"""Reviewer identity port.

The TriChurn API has NO authentication today. Phase 11 therefore does not invent any: the default authoriser rejects
every request, which keeps approve / reject / execute / feedback disabled. A real identity provider (a future phase)
implements ``Authorizer`` and is injected at the composition root.
"""
from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass
from typing import Protocol


@dataclass(frozen=True)
class Reviewer:
    user_id: str
    display_name: str


class Authorizer(Protocol):
    configured: bool

    def authenticate(self, headers: Mapping[str, str]) -> Reviewer | None: ...


class DenyAllAuthorizer:
    """Default: no identity provider is configured, so nobody is an authorised reviewer."""

    configured = False

    def authenticate(self, headers: Mapping[str, str]) -> Reviewer | None:
        return None
