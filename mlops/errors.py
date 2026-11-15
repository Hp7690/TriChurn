"""Phase 8 exceptions. Messages carry artifact NAMES and reason codes only - never filesystem paths."""
from __future__ import annotations


class MlopsError(Exception):
    """Base class for Phase 8 errors."""


class MlopsConfigurationError(MlopsError, ValueError):
    """A Phase 8 setting is malformed. Messages never echo the offending value."""


class ModelIntegrityError(MlopsError):
    """The model artifact is missing, unreadable or does not match the locked digest/version.

    ``reason`` is one of: missing, unreadable, sha256_mismatch, metadata_sha256_mismatch, version_mismatch,
    metadata_unreadable, invalid_expected_sha256.
    """

    def __init__(self, artifact: str, reason: str):
        super().__init__(f"model artifact '{artifact}': {reason}")
        self.artifact, self.reason = artifact, reason


class RegistryError(MlopsError):
    """MLflow tracking/registry could not complete an operation (never raised by ordinary prediction)."""
