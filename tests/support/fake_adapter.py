"""TEST-ONLY FAKE ADAPTER. IT IS NOT A MODEL AND MUST NEVER BE USED IN PRODUCTION.

It exists so the API layer (routing, validation, error handling, orchestration) can be tested without the Phase 1-5
code. The numbers it returns are arbitrary deterministic formulas with no relationship to the real churn model.
It lives under ``tests/`` on purpose: the ``app`` package contains no fake and ``create_app`` rejects any adapter whose
``is_test_double`` is True when ``environment == "production"``.
"""
from __future__ import annotations

import math
from collections.abc import Mapping
from typing import Any

from app.core.errors import capability_unavailable
from app.services.adapters.interface import (
    CAP_BUSINESS,
    CAP_EXPLAIN,
    CAP_MODEL,
    CAP_SEGMENT,
    ActionEvaluation,
    BusinessExplanation,
    BusinessResult,
    CheckResult,
    DecisionReason,
    ExplanationResult,
    FeatureContribution,
    PredictionResult,
    ReadinessReport,
    SegmentResult,
)

THRESHOLD = 0.34


class FakeAdapter:
    is_test_double = True

    def __init__(self, unavailable: set[str] | None = None, raises: dict[str, Exception] | None = None,
                 explain_probability_offset: float = 0.0):
        self.unavailable = set(unavailable or ())
        self.raises = dict(raises or {})
        self.explain_probability_offset = explain_probability_offset
        self.calls: list[tuple[str, dict[str, Any]]] = []

    # ------------------------------------------------------------------------------------------ plumbing
    def _enter(self, op: str, capability: str, **extra: Any) -> None:
        self.calls.append((op, dict(extra)))
        if capability in self.unavailable:
            raise capability_unavailable(capability)
        if op in self.raises:
            raise self.raises[op]

    @staticmethod
    def _p(customer: Mapping[str, Any]) -> float:
        z = -1.0 + 0.02 * customer["MonthlyCharges"] - 0.03 * customer["tenure"]
        z += 0.8 if customer["Contract"] == "Month-to-month" else -0.4
        return 1.0 / (1.0 + math.exp(-z))

    # --------------------------------------------------------------------------------------------- port
    def warm_up(self) -> None:
        return None

    def readiness(self) -> ReadinessReport:
        names = (CAP_MODEL, CAP_BUSINESS, CAP_EXPLAIN, CAP_SEGMENT)
        return ReadinessReport(tuple(CheckResult(n, n not in self.unavailable,
                                                 "unavailable" if n in self.unavailable else "ok") for n in names),
                               {"adapter": "TEST FAKE"})

    def predict(self, customer: Mapping[str, Any]) -> PredictionResult:
        self._enter("predict", CAP_MODEL, customer=dict(customer))
        p = self._p(customer)
        band = "HIGH" if p >= 0.5 else "MEDIUM" if p >= THRESHOLD else "LOW"
        return PredictionResult(p, p >= THRESHOLD, THRESHOLD, band, "fake_model", "0.0.0-test")

    def explain(self, customer: Mapping[str, Any]) -> ExplanationResult:
        self._enter("explain", CAP_EXPLAIN, customer=dict(customer))
        p = self._p(customer) + self.explain_probability_offset
        feats = [FeatureContribution("Contract", customer["Contract"], 0.9, "increases_churn"),
                 FeatureContribution("tenure", customer["tenure"], -0.5, "decreases_churn"),
                 FeatureContribution("MonthlyCharges", customer["MonthlyCharges"], 0.1, "increases_churn"),
                 FeatureContribution("gender", customer["gender"], 0.0, "neutral")]
        return ExplanationResult(p, int(p >= THRESHOLD), THRESHOLD, -1.0, "log_odds", 0.0, 1e-16, feats,
                                 "fake interpretation: describes the model, not causes", "0.0.0-test")

    def business(self, customer: Mapping[str, Any], churn_probability: float | None = None,
                 explanation: ExplanationResult | None = None) -> BusinessResult:
        self._enter("business", CAP_BUSINESS, customer=dict(customer), churn_probability=churn_probability,
                    explanation=explanation)
        p = self._p(customer) if churn_probability is None else churn_probability
        band = "HIGH" if p >= 0.5 else "MEDIUM" if p >= THRESHOLD else "LOW"
        clv = customer["MonthlyCharges"] * 12.0
        intervene = p >= THRESHOLD
        evals = [ActionEvaluation("no_action", "No action", 0.0, 0.0, True, None, 0.0, 0.0, 0.0),
                 ActionEvaluation("fake_offer", "Fake offer", 10.0, 0.2, True, None, clv * p * 0.2, 10.0,
                                  clv * p * 0.2 - 10.0)]
        enb = evals[1].expected_net_benefit if intervene else 0.0
        model_text = ("fake model text" if explanation is None else
                      "fake model text with drivers: " + ", ".join(f.source_feature for f in explanation.features[:2]))
        return BusinessResult(
            p, band, "XXX", clv, clv * p, "INTERVENE" if intervene else "DO_NOT_INTERVENE",
            "fake_offer" if intervene else "no_action", "Fake offer" if intervene else "No action",
            10.0 if intervene else 0.0, 0.2 if intervene else 0.0, evals[1].expected_benefit if intervene else 0.0,
            10.0 if intervene else 0.0, enb, [DecisionReason("FAKE_REASON", {"p": p})], ["fake reason"], evals,
            BusinessExplanation(model_text, "fake business text", "fake disclaimer"), "fake notice")

    def segment(self, customer: Mapping[str, Any]) -> SegmentResult:
        self._enter("segment", CAP_SEGMENT, customer=dict(customer))
        sid = 0 if customer["tenure"] < 12 else 1 if customer["tenure"] < 48 else 2
        return SegmentResult(sid, f"Fake segment {sid}", 1.25, "0.0.0-test", 3, 100 * (sid + 1), sid + 1, "LOW",
                             "fake note")
