"""User-facing exceptions. Messages are written for end users, not developers."""
from __future__ import annotations


class TriChurnError(Exception):
    """Base class for expected, user-correctable errors."""


class IngestionError(TriChurnError):
    """The file could not be read as a usable CSV."""


class ValidationError(TriChurnError):
    """The dataset failed one or more hard validation checks."""

    def __init__(self, report) -> None:  # report: ValidationReport
        self.report = report
        msgs = "; ".join(f"[{i.code}] {i.message}" for i in report.errors)
        super().__init__(f"Dataset rejected: {msgs}")


class TestSetAlreadyEvaluatedError(TriChurnError):
    """The held-out TEST split was already consumed for this locked model (it may be read once)."""

    __test__ = False  # not a pytest test class despite the name


class ArtifactIntegrityError(TriChurnError):
    """The model artifact failed its SHA-256 check or contradicts its trusted metadata (Phase 3)."""


class ExplainabilityInputError(TriChurnError):
    """The customer record(s) passed for explanation are missing features, malformed or non-finite (Phase 3)."""


class ExplainabilityError(TriChurnError):
    """The explainer cannot be built or a numerical consistency check failed (Phase 3)."""


class BusinessInputError(TriChurnError):
    """A value passed to the business layer is missing, non-finite, out of range or the wrong type (Phase 4)."""


class BusinessConfigError(TriChurnError):
    """The business / risk-band configuration is malformed or violates a business invariant (Phase 4)."""


class SegmentationConfigError(TriChurnError):
    """The segmentation configuration is malformed or asks for a forbidden clustering feature (Phase 5)."""


class SegmentationInputError(TriChurnError):
    """Customer data passed to segmentation is missing required columns or is unusable (Phase 5)."""
