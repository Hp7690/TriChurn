"""Phase 4 - business intelligence on top of the locked churn model: CLV, value at risk, expected net benefit,
intervention decisions, retention-action selection and what-if simulation.

Pure Python + numpy/pandas: no FastAPI, no backend/, no database. Business numbers are assumptions, not causal effects.
"""
from ml.business.clv import compute_clv, compute_clv_for_record, discounted_months
from ml.business.config import load_business_config, parse_business_config
from ml.business.decision import decide, resolve_policy
from ml.business.enb import compute_enb, expected_benefit, expected_cost, value_at_risk
from ml.business.engine import BusinessEngine
from ml.business.formatting import format_money, format_profile, render_reason
from ml.business.retention import evaluate_actions, select_best_action
from ml.business.risk_bands import assign_risk_band
from ml.business.schemas import (
    DO_NOT_INTERVENE,
    INTERVENE,
    BusinessConfig,
    CustomerBusinessProfile,
    DecisionResult,
    EnbBreakdown,
    RetentionAction,
)
from ml.business.what_if import Scenario, WhatIfResult, simulate, sweep_churn_probability, sweep_multiplier

__all__ = [
    "DO_NOT_INTERVENE", "INTERVENE", "BusinessConfig", "BusinessEngine", "CustomerBusinessProfile", "DecisionResult",
    "EnbBreakdown", "RetentionAction", "Scenario", "WhatIfResult", "assign_risk_band", "compute_clv",
    "compute_clv_for_record", "compute_enb", "decide", "discounted_months", "evaluate_actions", "expected_benefit",
    "expected_cost", "format_money", "format_profile", "load_business_config", "parse_business_config",
    "render_reason", "resolve_policy", "select_best_action", "simulate", "sweep_churn_probability",
    "sweep_multiplier", "value_at_risk",
]
