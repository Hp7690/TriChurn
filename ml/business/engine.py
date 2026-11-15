"""Customer -> business profile. Combines churn probability, CLV, risk band, ENB and the decision.

Takes the probability as an INPUT (from the Phase 2 artifact, e.g. ``ModelArtifact.predict_proba``); it never loads,
changes or re-scores the model.
"""
from __future__ import annotations

from collections.abc import Mapping
from typing import Any

import pandas as pd

from ml.business.clv import compute_clv_for_record
from ml.business.decision import decide, resolve_policy
from ml.business.explanation import build_business_explanation
from ml.business.formatting import render_reason
from ml.business.risk_bands import assign_risk_band
from ml.business.schemas import (
    BusinessConfig,
    BusinessExplanation,
    CustomerBusinessProfile,
    ExplanationLike,
)
from ml.business.validation import require_probability
from ml.errors import BusinessInputError


class BusinessEngine:
    """Stateless apart from its (immutable) configuration and the model's operating threshold."""

    def __init__(self, config: BusinessConfig, model_threshold: float | None = None):
        self.config = config
        self.model_threshold = None if model_threshold is None else require_probability(model_threshold,
                                                                                         "model_threshold")

    def profile(self, churn_probability: Any, record: Mapping[str, Any], customer_id: str | None = None
                ) -> CustomerBusinessProfile:
        p = require_probability(churn_probability)
        clv = compute_clv_for_record(record, self.config.clv)
        result = decide(clv.clv, p, self.config.actions, resolve_policy(self.config.policy, self.model_threshold))
        rec = result.recommended
        cur = self.config.currency
        return CustomerBusinessProfile(
            customer_id=None if customer_id is None else str(customer_id), churn_probability=p,
            risk_band=assign_risk_band(p, self.config.risk_bands), clv=clv.clv, value_at_risk=rec.enb.value_at_risk,
            recommended_action=rec.action.name, recommended_action_id=rec.action.action_id,
            action_cost=rec.enb.action_cost, action_success_rate=rec.enb.action_success_rate,
            expected_benefit=rec.enb.expected_benefit, expected_cost=rec.enb.expected_cost,
            expected_net_benefit=rec.enb.expected_net_benefit, intervention_decision=result.decision,
            decision_reasons=result.reasons,
            decision_reason_messages=tuple(render_reason(r, cur) for r in result.reasons),
            currency=cur.code, clv_detail=clv, action_evaluations=result.evaluations, policy=result.policy)

    def profile_frame(self, frame: pd.DataFrame, probabilities: Any, id_column: str | None = None
                      ) -> list[CustomerBusinessProfile]:
        """One profile per row; ``probabilities`` aligns with the rows (e.g. ``artifact.predict_proba(frame)``)."""
        probs = list(probabilities)
        if len(probs) != len(frame):
            raise BusinessInputError(f"Got {len(probs)} probabilities for {len(frame)} customers.")
        if id_column is not None and id_column not in frame.columns:
            raise BusinessInputError(f"id column '{id_column}' is not in the customer frame.")
        out = []
        for (_, row), p in zip(frame.iterrows(), probs, strict=True):
            out.append(self.profile(p, row.to_dict(), None if id_column is None else row[id_column]))
        return out

    def explain(self, profile: CustomerBusinessProfile, explanation: ExplanationLike | None = None,
                top_n: int = 3) -> BusinessExplanation:
        """MODEL EXPLANATION (from SHAP, if given) and BUSINESS DECISION as separate sections."""
        return build_business_explanation(profile, explanation, self.config.currency, top_n)
