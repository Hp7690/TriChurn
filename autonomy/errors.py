from __future__ import annotations


class AutonomyError(Exception):
    """Base class; messages are safe to show to API clients."""


class AutonomyInputError(AutonomyError, ValueError):
    pass


class AutonomyNotFoundError(AutonomyError):
    pass


class AutonomyConflictError(AutonomyError):
    """Invalid state transition, duplicate record, or an idempotency-key mismatch."""


class AutonomyForbiddenError(AutonomyError):
    """No authenticated, authorised reviewer."""


class FeatureDisabledError(AutonomyError):
    """A configured-off capability was requested."""
