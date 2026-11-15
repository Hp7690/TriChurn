"""Read-only port to the verified Phase 9 scored portfolio and priority ranking."""
from __future__ import annotations

from collections.abc import Sequence
from typing import Protocol

from retention.facade import RetentionFacade
from retention.models import Portfolio
from retention.prioritization import PriorityEntry


class RetentionSource(Protocol):
    def portfolio(self) -> Portfolio: ...

    def entries(self) -> Sequence[PriorityEntry]: ...

    def entry(self, customer_id: str) -> PriorityEntry | None: ...


class Phase9Source:
    """Adapter over the Phase 9 ``RetentionFacade``; it never writes to Phase 9 state."""

    def __init__(self, facade: RetentionFacade):
        self._facade = facade

    def portfolio(self) -> Portfolio:
        return self._facade.portfolio()

    def entries(self) -> Sequence[PriorityEntry]:
        return self._facade.index().entries

    def entry(self, customer_id: str) -> PriorityEntry | None:
        return self._facade.index().entry(customer_id)
