"""Domain errors. Messages are written to be safe to show to API clients (no paths, no internals)."""
from __future__ import annotations


class RetentionError(Exception):
    """Base class."""


class RetentionInputError(RetentionError, ValueError):
    """The caller supplied an invalid value."""


class RetentionNotFoundError(RetentionError):
    """A referenced campaign, customer or assignment does not exist."""



class PortfolioUnavailableError(RetentionError):
    """The scored portfolio could not be built (artifact, dataset or configuration problem).

    ``reason`` is a short code, never a path or exception text.
    """

    def __init__(self, reason: str):
        super().__init__(reason)
        self.reason = reason
