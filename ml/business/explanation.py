"""Business-readable explanation with MODEL EXPLANATION and BUSINESS DECISION kept apart.

Consumes any Phase 3 ``LocalExplanation``-shaped object (duck-typed; this module does not import shap). SHAP values
describe how features moved the model's score; they are never presented as causes of churn.
"""
from __future__ import annotations

from ml.business.formatting import format_money
from ml.business.schemas import (
    DO_NOT_INTERVENE,
    NON_CAUSAL_NOTE,
    BusinessExplanation,
    CurrencyConfig,
    CustomerBusinessProfile,
    ExplanationLike,
)

# Literals of ml.explainability.schemas.INCREASES_CHURN / DECREASES_CHURN (a test keeps them in sync).
INCREASES = "increases_churn"
DECREASES = "decreases_churn"


def _names(features: list, direction: str, n: int) -> list[str]:
    picked = [f for f in features if f.direction == direction][:n]     # input is already sorted by |SHAP|
    return [f"{f.source_feature} (value: {f.raw_value})" if getattr(f, "raw_value", None) is not None
            else f.source_feature for f in picked]


def build_business_explanation(profile: CustomerBusinessProfile, explanation: ExplanationLike | None,
                               currency: CurrencyConfig, top_n: int = 3) -> BusinessExplanation:
    m = lambda x: format_money(x, currency)  # noqa: E731
    if explanation is None:
        model_text = (f"The model scored this customer at churn probability {profile.churn_probability:.2f} "
                      f"(risk band {profile.risk_band}). No per-feature explanation was supplied.")
    else:
        up, down = _names(explanation.features, INCREASES, top_n), _names(explanation.features, DECREASES, top_n)
        parts = [f"The model scored this customer at churn probability {profile.churn_probability:.2f} "
                 f"(risk band {profile.risk_band})."]
        if up:
            parts.append("Features that contributed most toward a higher model score: " + ", ".join(up) + ".")
        if down:
            parts.append("Features that contributed most toward a lower model score: " + ", ".join(down) + ".")
        parts.append("These describe the model's score, not causes of churn.")
        model_text = " ".join(parts)

    if profile.intervention_decision == DO_NOT_INTERVENE:
        decision_text = (f"Under the configured policy no intervention is recommended (CLV {m(profile.clv)}, value at "
                         f"risk {m(profile.value_at_risk)}). " + " ".join(profile.decision_reason_messages))
    else:
        decision_text = (f"Under the configured assumptions, '{profile.recommended_action}' is the economically best "
                         f"eligible action: with an assumed success rate of {profile.action_success_rate:.2f} it has "
                         f"an estimated expected benefit of {m(profile.expected_benefit)} against a cost of "
                         f"{m(profile.expected_cost)}, i.e. an estimated expected net benefit of "
                         f"{m(profile.expected_net_benefit)} (CLV {m(profile.clv)}, value at risk "
                         f"{m(profile.value_at_risk)}).")
    return BusinessExplanation(model_text, decision_text, NON_CAUSAL_NOTE)
