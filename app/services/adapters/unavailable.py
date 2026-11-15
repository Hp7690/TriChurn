"""Placeholder used when the Phase 1-5 integration cannot be built. It is NOT a fake model.

Every capability answers ``503 INTEGRATION_NOT_CONFIGURED`` and ``/readiness`` reports why (as a code, never a path or
exception text). This is what a production deployment gets if the integration is missing: it fails closed.
"""
from __future__ import annotations

from collections.abc import Mapping
from typing import Any

from app.core.errors import integration_not_configured
from app.services.adapters.interface import (
    CAP_MODULES,
    BusinessResult,
    CheckResult,
    ExplanationResult,
    PredictionResult,
    ReadinessReport,
    SegmentResult,
)


class UnavailableAdapter:
    is_test_double = False

    def __init__(self, reason_code: str):
        self._reason = reason_code

    def warm_up(self) -> None:
        return None

    def readiness(self) -> ReadinessReport:
        return ReadinessReport((CheckResult(CAP_MODULES, False, self._reason),))

    def predict(self, customer: Mapping[str, Any]) -> PredictionResult:
        raise integration_not_configured()

    def explain(self, customer: Mapping[str, Any]) -> ExplanationResult:
        raise integration_not_configured()

    def business(self, customer: Mapping[str, Any], churn_probability: float | None = None,
                 explanation: ExplanationResult | None = None) -> BusinessResult:
        raise integration_not_configured()

    def segment(self, customer: Mapping[str, Any]) -> SegmentResult:
        raise integration_not_configured()
