"""Single source of truth for evidence statuses and metric metadata.

The API serialises these definitions and the frontend renders them; neither side keeps its own copy of a formula
or a limitation. A metric whose status is UNAVAILABLE or BLOCKED_BY_MISSING_DATA ALWAYS has ``value = None``.
"""
from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime
from enum import StrEnum
from typing import Any


class MetricStatus(StrEnum):
    ACTUAL = "ACTUAL"                          # read directly from observed data fields (still a snapshot)
    ESTIMATED = "ESTIMATED"                    # computed with explicit, confirmed assumptions
    PROXY = "PROXY"                            # stands in for a quantity that is not observed
    ILLUSTRATIVE = "ILLUSTRATIVE"              # depends on unconfirmed default assumptions; not for decisions
    UNAVAILABLE = "UNAVAILABLE"                # cannot be computed with the data supplied
    BLOCKED_BY_MISSING_DATA = "BLOCKED_BY_MISSING_DATA"   # a required data source does not exist


STATUSES = [s.value for s in MetricStatus]
_NULL_STATUSES = {MetricStatus.UNAVAILABLE, MetricStatus.BLOCKED_BY_MISSING_DATA}


@dataclass(frozen=True)
class MetricDefinition:
    key: str
    name: str
    description: str
    formula: str
    source_fields: tuple[str, ...]
    default_status: MetricStatus
    assumptions: tuple[str, ...] = ()
    limitations: tuple[str, ...] = ()
    unit: str = "currency"


def _d(key, name, description, formula, fields, status, assumptions=(), limitations=(), unit="currency"):
    return MetricDefinition(key, name, description, formula, tuple(fields), status, tuple(assumptions),
                            tuple(limitations), unit)


NOT_PROFIT = "Revenue/billing only - not profit; no acquisition, serving or margin cost exists in the data."
SNAPSHOT = "Single customer snapshot; no time-indexed history."

_DEFS = [
    _d("customers_total", "Customers analysed", "Unique customers after de-duplication.",
       "count(unique customerID)", ["customerID"], MetricStatus.ACTUAL, limitations=[SNAPSHOT], unit="count"),
    _d("observed_billing_total", "Observed cumulative billing",
       "Sum of TotalCharges over customers with a valid TotalCharges value.", "sum(TotalCharges where valid)",
       ["TotalCharges"], MetricStatus.ACTUAL,
       ["TotalCharges is treated as cumulative billing observed in the snapshot."],
       [NOT_PROFIT, "Excludes customers whose TotalCharges is missing/invalid (counted separately)."]),
    _d("observed_billing_avg", "Average observed billing", "Mean TotalCharges over valid rows.",
       "mean(TotalCharges where valid)", ["TotalCharges"], MetricStatus.ACTUAL, limitations=[NOT_PROFIT]),
    _d("monthly_recurring_total", "Recurring monthly charges", "Sum of current MonthlyCharges.",
       "sum(MonthlyCharges where valid)", ["MonthlyCharges"], MetricStatus.ACTUAL,
       ["MonthlyCharges is the current recurring monthly charge at snapshot time."], [NOT_PROFIT, SNAPSHOT]),
    _d("historical_clv_proxy", "Historical CLV proxy", "Observed cumulative billing used as a stand-in for realised "
       "lifetime value to date.", "TotalCharges", ["TotalCharges"], MetricStatus.PROXY,
       ["Cumulative billing approximates value delivered to date."],
       ["NOT realised lifetime value and NOT net of any cost.", "Says nothing about future value."]),
    _d("estimated_forward_value", "Scenario forward value",
       "Assumed future recurring billing for active customers.",
       "MonthlyCharges x sum_{t=1..H} (1+r)^-t, H = assumed remaining months for the contract type, r = monthly "
       "discount rate", ["MonthlyCharges", "Contract", "Churn"], MetricStatus.ILLUSTRATIVE,
       ["H comes from configs/revenue_intelligence.yaml and is a business ASSUMPTION, not derived from data.",
        "Already-churned customers contribute 0 forward value."],
       ["Not a forecast.", "Becomes ESTIMATED only after assumptions_confirmed: true.", NOT_PROFIT]),
    _d("estimated_clv", "Scenario CLV", "Observed billing plus scenario forward value.",
       "TotalCharges + forward_value", ["TotalCharges", "MonthlyCharges", "Contract", "Churn"],
       MetricStatus.ILLUSTRATIVE, ["See estimated_forward_value."],
       ["Customers without valid TotalCharges get no scenario CLV (UNAVAILABLE).", NOT_PROFIT]),
    _d("probability_adjusted_clv", "Probability-adjusted scenario CLV",
       "Scenario forward value scaled by (1 - p).", "TotalCharges + forward_value x (1 - p)",
       ["TotalCharges", "MonthlyCharges", "Contract", "Churn", "churn probability"], MetricStatus.ESTIMATED,
       ["p is a churn probability with VALIDATED_OUT_OF_SAMPLE provenance.",
        "p is treated as applying across the assumed horizon - a coarse simplification."],
       ["Unavailable unless a validated probability source is configured."]),
    _d("churned_billing_context", "Billing of already-churned customers",
       "Observed cumulative billing of customers labelled Churn = Yes in the snapshot.",
       "sum(TotalCharges where Churn = Yes)", ["TotalCharges", "Churn"], MetricStatus.ACTUAL,
       ["The Churn label records customers who had already left at snapshot time."],
       ["Historical context only. It is NOT revenue at risk and NOT a prediction."]),
    _d("churned_monthly_context", "Recurring charges of already-churned customers",
       "MonthlyCharges of customers labelled Churn = Yes.", "sum(MonthlyCharges where Churn = Yes)",
       ["MonthlyCharges", "Churn"], MetricStatus.ACTUAL,
       limitations=["Recurring revenue that was already lost at snapshot time; NOT revenue at risk."]),
    _d("rule_flagged_monthly_exposure", "Rule-flagged recurring exposure",
       "MonthlyCharges of active customers that match >= N configured risk indicators.",
       "sum(MonthlyCharges where Churn = No and indicators >= N)",
       ["MonthlyCharges", "Churn", "Contract", "tenure", "InternetService", "TechSupport"], MetricStatus.PROXY,
       ["Indicators are descriptive screening rules, not a probability."],
       ["UNWEIGHTED: flagged customers are not expected to churn at 100%.", "Not lost and not recoverable revenue.",
        NOT_PROFIT]),
    _d("rule_flagged_billing_exposure", "Rule-flagged observed billing",
       "Cumulative billing of the rule-flagged active customers.", "sum(TotalCharges for flagged customers)",
       ["TotalCharges"], MetricStatus.PROXY, limitations=["Historical billing associated with the flagged group; "
       "not a loss amount."]),
    _d("expected_monthly_exposure", "Probability-weighted monthly exposure",
       "Expected recurring monthly charges exposed to churn.", "sum(MonthlyCharges x churn_probability)",
       ["MonthlyCharges", "churn probability"], MetricStatus.ESTIMATED,
       ["Probabilities have VALIDATED_OUT_OF_SAMPLE provenance and are calibrated for the same horizon."],
       ["Unavailable unless a validated probability source is configured.",
        "Not guaranteed loss and not guaranteed recoverable revenue."]),
    _d("opportunity_count", "Rule-based opportunities",
       "Advisory service-gap/contract-review opportunities.", "count(recommendations)",
       ["InternetService", "OnlineSecurity", "OnlineBackup", "DeviceProtection", "TechSupport", "StreamingTV",
        "StreamingMovies", "Contract", "tenure"], MetricStatus.PROXY,
       ["A service gap is an observation, not purchase intent."],
       ["No conversion probability, price or uplift exists; all require human review."], unit="count"),
    _d("opportunity_revenue_uplift", "Opportunity revenue uplift", "Revenue expected from acting on opportunities.",
       "n/a", ["actual offer outcomes"], MetricStatus.BLOCKED_BY_MISSING_DATA,
       limitations=["No product prices, conversion outcomes or offer history exist."], unit="currency"),
    _d("tenure_cohort", "Tenure-based cohort metrics", "Customer groups by months of tenure.",
       "group by bucket(tenure)", ["tenure", "Contract", "MonthlyCharges", "TotalCharges", "Churn"],
       MetricStatus.PROXY, ["Tenure buckets approximate lifecycle stage."],
       ["TENURE_BASED_PROXY: not acquisition-month cohorts; cross-sectional, so survivor bias applies."],
       unit="mixed"),
    _d("churn_rate", "Observed churn share", "Share of customers labelled Churn = Yes.",
       "count(Churn = Yes) / count(Churn known)", ["Churn"], MetricStatus.ACTUAL,
       limitations=["Historical label in a snapshot; not a forecast."], unit="ratio"),
    _d("forecast_readiness", "Forecast readiness", "Whether real time-indexed revenue supports forecasting.",
       "validation of period/customer_id/revenue history", ["period", "customer_id", "revenue"],
       MetricStatus.BLOCKED_BY_MISSING_DATA, limitations=["No forecast is produced without real history."],
       unit="state"),
]
METRICS: dict[str, MetricDefinition] = {d.key: d for d in _DEFS}


def _now() -> str:
    return datetime.now(UTC).isoformat(timespec="seconds")


def make_metric(key: str, value: Any, status: MetricStatus | str | None = None, reason: str | None = None,
                calculated_at: str | None = None, extra_assumptions: list[str] | None = None) -> dict[str, Any]:
    """Build a serialisable metric. Null statuses force ``value = None`` so unavailable never renders as zero."""
    d = METRICS[key]
    st = MetricStatus(status) if status is not None else d.default_status
    if value is None and st not in _NULL_STATUSES:
        st = MetricStatus.UNAVAILABLE
    if st in _NULL_STATUSES:
        value = None
    if isinstance(value, float):
        value = round(value, 4)
    return {"key": d.key, "name": d.name, "description": d.description, "value": value, "unit": d.unit,
            "status": st.value, "formula": d.formula, "source_fields": list(d.source_fields),
            "assumptions": list(d.assumptions) + list(extra_assumptions or []), "limitations": list(d.limitations),
            "reason": reason, "calculated_at": calculated_at or _now()}


def registry_dump() -> list[dict[str, Any]]:
    return [{"key": d.key, "name": d.name, "description": d.description, "formula": d.formula,
             "source_fields": list(d.source_fields), "default_status": d.default_status.value,
             "assumptions": list(d.assumptions), "limitations": list(d.limitations), "unit": d.unit}
            for d in METRICS.values()]
