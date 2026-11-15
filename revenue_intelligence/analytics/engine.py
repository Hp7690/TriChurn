"""RevenueEngine: composes CLV, revenue-at-risk, opportunities, cohorts and forecast readiness into API-ready dicts.

Framework-free (no FastAPI/pydantic). Every figure is wrapped by ``make_metric`` with an evidence status and metadata.
It never trains a churn model and never writes data.
"""
from __future__ import annotations

from datetime import UTC, datetime
from typing import Any

import numpy as np
import pandas as pd

from .. import PACKAGE_VERSION
from ..availability import MetricStatus, make_metric, registry_dump
from ..clv import calculator as clvc
from ..clv import segmentation as seg
from ..cohorts import tenure as coh
from ..cohorts.acquisition import acquisition_cohorts
from ..errors import RevenueInputError
from ..forecasting import models as fmodels
from ..forecasting import timeseries as ts
from ..opportunities import rules as opp
from ..revenue_risk import exposure as rx
from .config import SEGMENT_LABELS, RevenueConfig
from .dataset import prepare

METHODOLOGY_NOTE = ("Revenue is billing/recurring charges, not profit. Values are computed from a single customer "
                    "snapshot; each metric carries an evidence status. Nothing is a guaranteed loss, recovery "
                    "or uplift.")


def _clean(v: Any) -> Any:
    if isinstance(v, (np.integer,)):
        return int(v)
    if isinstance(v, (np.floating, float)):
        return None if (v != v or v in (float("inf"), float("-inf"))) else float(v)
    if isinstance(v, (np.bool_,)):
        return bool(v)
    if isinstance(v, dict):
        return {str(k): _clean(x) for k, x in v.items()}
    if isinstance(v, (list, tuple)):
        return [_clean(x) for x in v]
    return v


def paginate(items: list, page: int, size: int, max_size: int) -> dict[str, Any]:
    if page < 1 or size < 1 or size > max_size:
        raise RevenueInputError(f"page must be >= 1 and page_size between 1 and {max_size}")
    total = len(items)
    start = (page - 1) * size
    return {"items": items[start:start + size], "total": total, "page": page, "page_size": size,
            "page_count": max(1, -(-total // size))}


class RevenueEngine:
    def __init__(self, raw: pd.DataFrame, config: RevenueConfig, forecast_frame: pd.DataFrame | None = None,
                 source_label: str = "customer snapshot"):
        self.config, self.source_label = config, source_label
        self.forecast_frame = forecast_frame
        base, self.quality = prepare(raw, config.quality, config.data.probability_column,
                                     config.data.probability_provenance)
        df = clvc.add_clv_columns(base, config.clv)
        metric_col = seg.metric_column(config.clv)
        df["value_segment"], self.thresholds = seg.assign(df[metric_col], config.clv)
        df["tenure_bucket"] = coh.assign_buckets(df["tenure_n"], config.cohorts)
        df["lifecycle_group"] = coh.assign_lifecycle(df["tenure_n"], config.cohorts)
        self.df = rx.add_risk_columns(df, config.risk)
        self._opps: list[dict] | None = None
        self.calculated_at = datetime.now(UTC).isoformat(timespec="seconds")

    # ------------------------------------------------------------------ helpers
    def _m(self, key: str, value: Any, status: MetricStatus | None = None, reason: str | None = None, **kw: Any):
        return make_metric(key, _clean(value), status, reason, self.calculated_at, **kw)

    def _scenario(self) -> tuple[MetricStatus, str | None]:
        st = clvc.scenario_status(self.config.clv)
        if st is MetricStatus.UNAVAILABLE:
            return st, "Scenario CLV is disabled, or no remaining-lifetime assumptions / Contract column exist."
        return st, None

    def _churn_known(self) -> bool:
        return bool(self.df["churned"].isin([True, False]).any())

    def _page(self, items: list, page: int, size: int | None) -> dict[str, Any]:
        a = self.config.api
        return paginate(items, page, size or a.default_page_size, a.max_page_size)

    def _meta(self) -> dict[str, Any]:
        return {"calculated_at": self.calculated_at, "data_source": self.source_label,
                "methodology_note": METHODOLOGY_NOTE, "package_version": PACKAGE_VERSION}

    # ------------------------------------------------------------------ CLV
    def clv_summary(self) -> dict[str, Any]:
        d, cfg = self.df, self.config.clv
        st, reason = self._scenario()
        b = d["billing"].dropna()
        scen_assump = [f"Assumed remaining months: {cfg.remaining_months}",
                       f"Monthly discount rate: {cfg.monthly_discount_rate}",
                       "Assumptions confirmed by a business owner." if cfg.assumptions_confirmed
                       else "Assumptions are UNCONFIRMED defaults, so scenario values are ILLUSTRATIVE."]
        p_ok, p_reason = rx.probability_status(d)
        adj = d["probability_adjusted_clv"]
        metrics = [
            self._m("customers_total", len(d)),
            self._m("observed_billing_total", float(b.sum()) if len(b) else None, reason=None if len(b) else
                    "No valid TotalCharges values."),
            self._m("observed_billing_avg", clvc.mean_or_none(d["billing"])),
            self._m("historical_clv_proxy", clvc.mean_or_none(d["billing"]),
                    reason="Average of observed cumulative billing per customer."),
            self._m("estimated_forward_value", clvc.mean_or_none(d["forward_value"]), st, reason,
                    extra_assumptions=scen_assump),
            self._m("estimated_clv", clvc.mean_or_none(d["estimated_clv"]), st, reason,
                    extra_assumptions=scen_assump),
            self._m("probability_adjusted_clv", clvc.mean_or_none(adj) if p_ok else None,
                    MetricStatus.ESTIMATED if p_ok else MetricStatus.UNAVAILABLE, None if p_ok else p_reason),
        ]
        q = self.quality
        return {**self._meta(), "metrics": metrics,
                "scenario": {"status": st.value, "assumptions_confirmed": cfg.assumptions_confirmed,
                             "remaining_months_by_contract": cfg.remaining_months,
                             "monthly_discount_rate": cfg.monthly_discount_rate, "reason": reason},
                "distribution_observed_billing": clvc.distribution(d["billing"]),
                "distribution_estimated_clv": clvc.distribution(d["estimated_clv"]),
                "distribution_status": MetricStatus.ACTUAL.value,
                "distribution_observed_billing_status": MetricStatus.ACTUAL.value,
                "distribution_estimated_clv_status": st.value,
                "customers_without_valid_billing": int(d["billing"].isna().sum()),
                "customers_with_inconsistent_billing": int(d["billing_inconsistent"].sum()),
                "data_quality": q.as_dict()}

    CLV_SORT = {"customer_id": "customerID", "observed_billing": "billing", "estimated_clv": "estimated_clv",
                "monthly_charges": "monthly", "tenure": "tenure_n"}

    def _clv_rows(self, d: pd.DataFrame) -> list[dict]:
        st, _ = self._scenario()
        rows = []
        for r in d.itertuples(index=False):
            rows.append(_clean({
                "customer_id": r.customerID, "contract": getattr(r, "Contract", None), "tenure_months": r.tenure_n,
                "monthly_charges": r.monthly, "observed_billing": r.billing,
                "observed_billing_status": "ACTUAL" if pd.notna(r.billing) else "UNAVAILABLE",
                "estimated_forward_value": r.forward_value, "estimated_clv": r.estimated_clv,
                "estimated_clv_status": st.value if pd.notna(r.estimated_clv) else "UNAVAILABLE",
                "value_segment": r.value_segment, "churned": r.churned if r.churned in (True, False) else None,
                "billing_inconsistent": bool(r.billing_inconsistent)}))
        return rows

    def clv_customers(self, page: int = 1, page_size: int | None = None, segment: str | None = None,
                      sort_by: str = "customer_id", descending: bool = False,
                      customer_id: str | None = None) -> dict[str, Any]:
        if sort_by not in self.CLV_SORT:
            raise RevenueInputError(f"sort_by must be one of {sorted(self.CLV_SORT)}")
        if segment and segment not in (*SEGMENT_LABELS, seg.UNASSIGNED):
            raise RevenueInputError("unknown value segment")
        d = self.df
        if segment:
            d = d[d["value_segment"] == segment]
        if customer_id:
            d = d[d["customerID"] == customer_id]
        col = self.CLV_SORT[sort_by]
        d = d.sort_values([col, "customerID"], ascending=[not descending, True], na_position="last")
        a = self.config.api
        size = page_size or a.default_page_size
        pg = paginate([None] * len(d), page, size, a.max_page_size)
        window = d.iloc[(page - 1) * size: page * size]
        pg["items"] = self._clv_rows(window)
        return {**self._meta(), **pg}

    def clv_segments(self) -> dict[str, Any]:
        cfg = self.config.clv
        col = seg.metric_column(cfg)
        avail = self.df[col].notna().any()
        st = MetricStatus.ACTUAL if col == "billing" else self._scenario()[0]
        reason = None if avail else (f"Segmentation metric '{cfg.seg_metric}' has no valid values.")
        return {**self._meta(), "metric": cfg.seg_metric, "method": cfg.seg_method,
                "metric_status": (st if avail else MetricStatus.UNAVAILABLE).value, "reason": reason,
                "thresholds": self.thresholds, "labels": list(SEGMENT_LABELS),
                "note": "Business value tiers. Not the Phase 5 ML behavioural segments.",
                "segments": _clean(seg.segment_table(self.df, self.df["value_segment"]))}

    # ------------------------------------------------------------------ revenue at risk
    def risk_summary(self) -> dict[str, Any]:
        d = self.df
        known = self._churn_known()
        flagged = d[d["rule_flagged"]]
        churned = d[d["churned"] == True]    # noqa: E712
        p_ok, p_reason = rx.probability_status(d)
        no_churn = "Churn status is unknown, so already-churned customers cannot be separated from active ones."
        exp = clvc.sum_or_none(d[rx.active_mask(d)]["expected_exposure"]) if p_ok else None
        metrics = [
            self._m("churned_monthly_context", clvc.sum_or_none(churned["monthly"]) if known else None,
                    reason=None if known else no_churn),
            self._m("churned_billing_context", clvc.sum_or_none(churned["billing"]) if known else None,
                    reason=None if known else no_churn),
            self._m("rule_flagged_monthly_exposure", clvc.sum_or_none(flagged["monthly"]) if known and len(flagged)
                    else (0.0 if known else None), MetricStatus.PROXY if known else MetricStatus.UNAVAILABLE,
                    None if known else no_churn),
            self._m("rule_flagged_billing_exposure", clvc.sum_or_none(flagged["billing"]) if known and len(flagged)
                    else (0.0 if known else None), MetricStatus.PROXY if known else MetricStatus.UNAVAILABLE,
                    None if known else no_churn),
            self._m("expected_monthly_exposure", exp, MetricStatus.ESTIMATED if p_ok else MetricStatus.UNAVAILABLE,
                    None if p_ok else p_reason),
        ]
        r = self.config.risk
        by_c = rx.group_table(d, d["Contract"] if "Contract" in d.columns else pd.Series("Unknown", index=d.index))
        by_t = rx.group_table(d, d["tenure_bucket"], coh.bucket_labels(self.config.cohorts.edges))
        by_s = rx.group_table(d, d["value_segment"], [*SEGMENT_LABELS, seg.UNASSIGNED])
        return {**self._meta(), "metrics": metrics, "flagged_customers": int(len(flagged)),
                "active_customers": int(rx.active_mask(d).sum()),
                "probability_weighting": {"available": p_ok, "reason": p_reason,
                                          "provenance": d.attrs.get("probability_provenance", "UNKNOWN")},
                "rule_definition": {"indicators": {"month_to_month": r.month_to_month,
                                                   "max_tenure_months": r.max_tenure_months,
                                                   "internet_without_tech_support": r.internet_without_tech_support},
                                    "min_indicators_to_flag": r.min_indicators,
                                    "status": "PROXY", "is_probability": False},
                "by_contract": _clean(by_c), "by_tenure_group": _clean(by_t), "by_value_segment": _clean(by_s),
                "warnings": ["Exposed revenue is not lost revenue and not guaranteed recoverable revenue.",
                             "The Churn label is historical; it is not used as a prediction."]}

    def risk_customers(self, page: int = 1, page_size: int | None = None, contract: str | None = None,
                       segment: str | None = None, tenure_group: str | None = None) -> dict[str, Any]:
        d = self.df[self.df["rule_flagged"]]
        if contract:
            d = d[d["Contract"] == contract] if "Contract" in d.columns else d.iloc[0:0]
        if segment:
            d = d[d["value_segment"] == segment]
        if tenure_group:
            d = d[d["tenure_bucket"] == tenure_group]
        d = d.sort_values(["monthly", "customerID"], ascending=[False, True])
        a = self.config.api
        size = page_size or a.default_page_size
        pg = paginate([None] * len(d), page, size, a.max_page_size)
        rows = []
        for r in d.iloc[(page - 1) * size: page * size].itertuples(index=False):
            has_p = pd.notna(r.expected_exposure)
            rows.append(_clean({
                "customer_id": r.customerID, "contract": getattr(r, "Contract", None), "tenure_months": r.tenure_n,
                "tenure_group": r.tenure_bucket, "value_segment": r.value_segment, "monthly_charges": r.monthly,
                "observed_billing": r.billing, "indicators": list(r.risk_indicator_names),
                "indicator_count": r.risk_indicator_count,
                "exposure_basis": "RULE_FLAGGED_UNWEIGHTED", "exposure_status": "PROXY",
                "churn_probability": r.probability if has_p else None,
                "expected_monthly_exposure": r.expected_exposure if has_p else None}))
        pg["items"] = rows
        return {**self._meta(), **pg}

    # ------------------------------------------------------------------ opportunities
    def _opportunities(self) -> list[dict]:
        if self._opps is None:
            self._opps = opp.build_recommendations(self.df, self.config.opportunities)
        return self._opps

    def opportunities_summary(self) -> dict[str, Any]:
        recs = self._opportunities()
        elig = [r for r in recs if r["eligibility"] == opp.ELIGIBLE]
        from collections import Counter
        by_type = Counter(r["recommendation_type"] for r in elig)
        by_target = Counter(r["suggested_category"] for r in elig)
        by_seg = Counter(r["value_segment"] for r in elig)
        by_elig = Counter(r["eligibility"] for r in recs)
        by_conf = Counter(r["data_confidence"] for r in elig)
        return {**self._meta(), "metrics": [self._m("opportunity_count", len(elig)),
                                            self._m("opportunity_revenue_uplift", None,
                                                    reason="No prices, offer history or conversion outcomes exist.")],
                "customers_with_opportunity": len({r["customer_id"] for r in elig}),
                "total_recommendations": len(recs), "eligible_recommendations": len(elig),
                "by_type": dict(by_type), "by_target": dict(by_target), "by_value_segment": dict(by_seg),
                "by_eligibility": dict(by_elig), "by_data_confidence": dict(by_conf),
                "requires_human_review": True,
                "warnings": ["Rule-based opportunities, not purchase propensities.",
                             "No conversion probability, price or revenue uplift is estimated.",
                             "Nothing is sent to customers; every item needs human review."]}

    def opportunities_customers(self, page: int = 1, page_size: int | None = None, rtype: str | None = None,
                                eligibility: str | None = None, segment: str | None = None,
                                customer_id: str | None = None) -> dict[str, Any]:
        if rtype and rtype not in opp.TYPES:
            raise RevenueInputError(f"recommendation_type must be one of {list(opp.TYPES)}")
        recs = [r for r in self._opportunities()
                if (not rtype or r["recommendation_type"] == rtype)
                and (not eligibility or r["eligibility"] == eligibility)
                and (not segment or r["value_segment"] == segment)
                and (not customer_id or r["customer_id"] == customer_id)]
        recs.sort(key=lambda r: (r["customer_id"], r["recommendation_type"], r["suggested_category"]))
        return {**self._meta(), **self._page(_clean(recs), page, page_size)}

    # ------------------------------------------------------------------ cohorts
    def cohort_tenure(self) -> dict[str, Any]:
        d, cfg = self.df, self.config.cohorts
        life_order = list(cfg.lifecycle)
        contract = d["Contract"] if "Contract" in d.columns else pd.Series(coh.UNKNOWN, index=d.index)
        return {**self._meta(), "method": coh.METHOD, "status": "PROXY",
                "limitations": ["Tenure-based proxy, not acquisition-month cohorts.",
                                "Cross-sectional snapshot: survivor bias applies."],
                "tenure_buckets": _clean(coh.aggregate(d, d["tenure_bucket"], coh.bucket_labels(cfg.edges))),
                "lifecycle_groups": _clean(coh.aggregate(d, d["lifecycle_group"], life_order)),
                "contract_cohorts": _clean(coh.aggregate(d, contract, sorted(contract.dropna().unique())))}

    def cohort_summary(self) -> dict[str, Any]:
        t = self.cohort_tenure()
        return {**self._meta(), "method": coh.METHOD, "status": "PROXY",
                "metrics": [self._m("tenure_cohort", len(t["tenure_buckets"]),
                                    reason="Number of populated tenure buckets.")],
                "supported_now": ["Tenure-based cohorts", "Contract-based cohorts", "Lifecycle groups",
                                  "Churn comparison by tenure bucket", "Average monthly charges by bucket",
                                  "Customer value by bucket"],
                "blocked_by_missing_data": [{"analysis": a, "status": "BLOCKED_BY_MISSING_DATA", "reason": r}
                                            for a, r in coh.UNSUPPORTED],
                "acquisition_cohorts": acquisition_cohorts(None, None),
                "tenure_buckets": t["tenure_buckets"], "limitations": t["limitations"]}

    # ------------------------------------------------------------------ forecasting
    def forecast_readiness(self) -> dict[str, Any]:
        report, _ = ts.validate(self.forecast_frame, self.config.forecast)
        return self._forecast_payload(report)

    def forecast_validate(self, rows: list[dict[str, Any]], run_backtest: bool = False) -> dict[str, Any]:
        cfg = self.config.forecast
        if len(rows) > cfg.max_rows:
            raise RevenueInputError(f"at most {cfg.max_rows} rows may be validated per request")
        frame = pd.DataFrame(rows) if rows else None
        report, series = ts.validate(frame, cfg)
        payload = self._forecast_payload(report)
        payload["backtest"] = None
        if run_backtest:
            if series is None:
                payload["backtest"] = {"status": "UNAVAILABLE", "reason": "No backtest: the data did not reach "
                                       "FORECAST_READY."}
            else:
                payload["backtest"] = fmodels.evaluate(series, cfg.holdout)
        return payload

    def _forecast_payload(self, report: ts.ReadinessReport) -> dict[str, Any]:
        ready = report.state == ts.READY
        return {**self._meta(), "state": report.state, "readiness": report.as_dict(), "schema": ts.SCHEMA,
                "metrics": [self._m("forecast_readiness", report.state,
                                    MetricStatus.ACTUAL if ready else MetricStatus.BLOCKED_BY_MISSING_DATA,
                                    None if ready else "; ".join(report.reasons))],
                "requirements": {"min_periods": self.config.forecast.min_periods,
                                 "min_periods_for_seasonality": self.config.forecast.min_periods_seasonality,
                                 "max_missing_period_share": self.config.forecast.max_missing_share,
                                 "frequency": "monthly", "model_trained": False, "forecast_produced": False},
                "note": "Validation only. No model is trained and no forecast is produced by this endpoint."}

    # ------------------------------------------------------------------ availability + summary
    def availability(self) -> dict[str, Any]:
        q = self.quality
        st, reason = self._scenario()
        p_ok, p_reason = rx.probability_status(self.df)
        fr = ts.validate(self.forecast_frame, self.config.forecast)[0]
        has = lambda c: c not in q.missing_columns    # noqa: E731
        modules = [
            {"module": "Observed billing (TotalCharges)", "status": "ACTUAL" if has("TotalCharges") else
             "UNAVAILABLE", "detail": "TotalCharges present." if has("TotalCharges") else "Column missing."},
            {"module": "Scenario CLV", "status": st.value, "detail": reason or "Assumption-driven scenario."},
            {"module": "Probability-adjusted CLV / weighted exposure",
             "status": "ESTIMATED" if p_ok else "UNAVAILABLE", "detail": p_reason},
            {"module": "Rule-flagged revenue exposure", "status": "PROXY" if self._churn_known() else "UNAVAILABLE",
             "detail": "Screening rules over active customers." if self._churn_known() else "Churn column missing."},
            {"module": "Upsell / cross-sell rules", "status": "PROXY",
             "detail": "Rule-based, advisory, human-reviewed."},
            {"module": "Tenure cohorts", "status": "PROXY", "detail": coh.METHOD},
            {"module": "Acquisition-month cohorts", "status": "BLOCKED_BY_MISSING_DATA",
             "detail": "No signup dates or dated revenue."},
            {"module": "Revenue forecasting", "status": "BLOCKED_BY_MISSING_DATA" if fr.state != ts.READY else "ACTUAL",
             "detail": fr.state},
            {"module": "Opportunity revenue uplift", "status": "BLOCKED_BY_MISSING_DATA",
             "detail": "No prices or conversion outcomes."},
            {"module": "Profit / margin", "status": "BLOCKED_BY_MISSING_DATA",
             "detail": "No cost data exists; all values are revenue."},
        ]
        return {**self._meta(), "modules": modules, "data_quality": q.as_dict(), "status_legend": {
            "ACTUAL": "Observed in the data snapshot.", "ESTIMATED": "Computed from confirmed assumptions.",
            "PROXY": "Stands in for an unobserved quantity.", "ILLUSTRATIVE": "Unconfirmed default assumptions.",
            "UNAVAILABLE": "Cannot be computed from the supplied data.",
            "BLOCKED_BY_MISSING_DATA": "A required data source does not exist."},
            "metric_definitions": registry_dump(),
            "independence": {"requires_phase_9": False, "requires_phase_11": False}}

    def summary(self) -> dict[str, Any]:
        clv, risk = self.clv_summary(), self.risk_summary()
        opps = self.opportunities_summary()
        known = self.df["churned"].dropna()
        churn = self._m("churn_rate", float((known == True).mean()) if len(known) else None,    # noqa: E712
                        reason=None if len(known) else "No Churn labels.")
        monthly = self._m("monthly_recurring_total", clvc.sum_or_none(self.df["monthly"]))
        by_key = {m["key"]: m for m in clv["metrics"] + risk["metrics"] + opps["metrics"]}
        headline = [by_key["customers_total"], by_key["observed_billing_total"], monthly,
                    by_key["estimated_clv"], churn, by_key["rule_flagged_monthly_exposure"],
                    by_key["expected_monthly_exposure"], by_key["opportunity_count"]]
        return {**self._meta(), "headline_metrics": headline, "clv": {"segments": self.clv_segments()["segments"]},
                "risk": {"by_contract": risk["by_contract"], "by_tenure_group": risk["by_tenure_group"],
                         "flagged_customers": risk["flagged_customers"]},
                "opportunities": {"by_type": opps["by_type"], "customers_with_opportunity":
                                  opps["customers_with_opportunity"]},
                "cohorts": self.cohort_tenure()["tenure_buckets"],
                "forecast_state": self.forecast_readiness()["state"],
                "data_quality": self.quality.as_dict(), "warnings": [METHODOLOGY_NOTE]}
