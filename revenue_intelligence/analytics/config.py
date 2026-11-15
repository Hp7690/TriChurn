"""Typed, validated configuration for Phase 12 (loaded from configs/revenue_intelligence.yaml)."""
from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import yaml

from ..errors import RevenueConfigError

PROVENANCES = ("VALIDATED_OUT_OF_SAMPLE", "IN_SAMPLE", "UNKNOWN")
SEGMENT_LABELS = ("Low Value", "Medium Value", "High Value", "Premium Value")


@dataclass(frozen=True)
class DataConfig:
    candidate_paths: tuple[str, ...] = ()
    max_file_bytes: int = 20_000_000
    max_rows: int = 200_000
    probability_column: str | None = None
    probability_provenance: str = "UNKNOWN"


@dataclass(frozen=True)
class QualityConfig:
    ratio_min: float = 0.25
    ratio_max: float = 4.0


@dataclass(frozen=True)
class ClvConfig:
    scenario_enabled: bool = True
    assumptions_confirmed: bool = False
    remaining_months: dict[str, float] = field(default_factory=dict)
    monthly_discount_rate: float = 0.0
    seg_metric: str = "observed_billing"
    seg_method: str = "quantile"
    quantiles: tuple[float, float, float] = (0.25, 0.50, 0.90)
    absolute: tuple[float, float, float] = (500.0, 2000.0, 5000.0)


@dataclass(frozen=True)
class RiskConfig:
    month_to_month: bool = True
    max_tenure_months: int = 12
    internet_without_tech_support: bool = True
    min_indicators: int = 2


@dataclass(frozen=True)
class CohortConfig:
    edges: tuple[int, ...] = (0, 6, 12, 24, 48)
    lifecycle: dict[str, tuple[int, int | None]] = field(default_factory=dict)


@dataclass(frozen=True)
class OpportunityConfig:
    protective: tuple[str, ...] = ("OnlineSecurity", "OnlineBackup", "DeviceProtection", "TechSupport")
    streaming: tuple[str, ...] = ("StreamingTV", "StreamingMovies")
    contract_min_tenure: int = 12
    bundle_max_protective: int = 1


@dataclass(frozen=True)
class ForecastConfig:
    frequency: str = "M"
    min_periods: int = 24
    min_periods_seasonality: int = 36
    max_missing_share: float = 0.10
    max_rows: int = 50_000
    holdout: int = 6


@dataclass(frozen=True)
class ApiConfig:
    default_page_size: int = 25
    max_page_size: int = 200


@dataclass(frozen=True)
class RevenueConfig:
    data: DataConfig = field(default_factory=DataConfig)
    quality: QualityConfig = field(default_factory=QualityConfig)
    clv: ClvConfig = field(default_factory=ClvConfig)
    risk: RiskConfig = field(default_factory=RiskConfig)
    cohorts: CohortConfig = field(default_factory=CohortConfig)
    opportunities: OpportunityConfig = field(default_factory=OpportunityConfig)
    forecast: ForecastConfig = field(default_factory=ForecastConfig)
    api: ApiConfig = field(default_factory=ApiConfig)


def _need(cond: bool, message: str) -> None:
    if not cond:
        raise RevenueConfigError(message)


def default_config() -> RevenueConfig:
    return RevenueConfig(
        clv=ClvConfig(remaining_months={"Month-to-month": 6, "One year": 12, "Two year": 24}),
        cohorts=CohortConfig(lifecycle={"New": (0, 6), "Early": (7, 24), "Established": (25, 48), "Loyal": (49, None)}))


def parse_config(raw: dict[str, Any]) -> RevenueConfig:
    """Validate a raw mapping. Unknown top-level sections are rejected so typos never pass silently."""
    _need(isinstance(raw, dict), "configuration must be a mapping")
    known = {"data", "quality", "clv", "revenue_risk", "cohorts", "opportunities", "forecast", "api"}
    _need(set(raw) <= known, f"unknown configuration sections: {sorted(set(raw) - known)}")
    base = default_config()
    d = raw.get("data") or {}
    prob = d.get("probability") or {}
    provenance = str(prob.get("provenance", "UNKNOWN"))
    _need(provenance in PROVENANCES, f"probability.provenance must be one of {PROVENANCES}")
    data = DataConfig(tuple(d.get("candidate_paths") or ()), int(d.get("max_file_bytes", 20_000_000)),
                      int(d.get("max_rows", 200_000)), prob.get("column"), provenance)
    _need(data.max_rows > 0 and data.max_file_bytes > 0, "data limits must be positive")

    q = raw.get("quality") or {}
    quality = QualityConfig(float(q.get("consistency_ratio_min", 0.25)), float(q.get("consistency_ratio_max", 4.0)))
    _need(0 < quality.ratio_min < quality.ratio_max, "quality ratio band invalid")

    c = raw.get("clv") or {}
    sc, sg = c.get("scenario") or {}, c.get("segmentation") or {}
    months = {str(k): float(v) for k, v in (sc.get("remaining_months_by_contract")
                                            or base.clv.remaining_months).items()}
    _need(all(v >= 0 for v in months.values()), "remaining months must be >= 0")
    rate = float(sc.get("monthly_discount_rate", 0.0))
    _need(0 <= rate < 1, "monthly_discount_rate must be in [0, 1)")
    metric, method = str(sg.get("metric", "observed_billing")), str(sg.get("method", "quantile"))
    _need(metric in ("observed_billing", "estimated_clv"), "segmentation.metric invalid")
    _need(method in ("quantile", "absolute"), "segmentation.method invalid")
    quant = tuple(float(x) for x in sg.get("quantiles", (0.25, 0.5, 0.9)))
    absol = tuple(float(x) for x in sg.get("absolute_thresholds", (500.0, 2000.0, 5000.0)))
    _need(len(quant) == 3 and 0 < quant[0] < quant[1] < quant[2] < 1, "quantiles must be 3 increasing values in (0,1)")
    _need(len(absol) == 3 and 0 <= absol[0] < absol[1] < absol[2], "absolute thresholds must be 3 increasing values")
    clv = ClvConfig(bool(sc.get("enabled", True)), bool(sc.get("assumptions_confirmed", False)), months, rate,
                    metric, method, quant, absol)  # type: ignore[arg-type]

    r = raw.get("revenue_risk") or {}
    ind = r.get("rule_indicators") or {}
    risk = RiskConfig(bool(ind.get("month_to_month", True)), int(ind.get("max_tenure_months", 12)),
                      bool(ind.get("internet_without_tech_support", True)), int(r.get("min_indicators_to_flag", 2)))
    active = sum([risk.month_to_month, risk.max_tenure_months > 0, risk.internet_without_tech_support])
    _need(1 <= risk.min_indicators <= max(active, 1), "min_indicators_to_flag must be between 1 and the number of "
                                                      "active indicators")

    co = raw.get("cohorts") or {}
    edges = tuple(int(x) for x in co.get("tenure_bucket_edges", (0, 6, 12, 24, 48)))
    _need(len(edges) >= 2 and edges[0] == 0 and list(edges) == sorted(set(edges)),
          "tenure_bucket_edges must start at 0 and be strictly increasing")
    life = {str(k): (int(v[0]), None if v[1] is None else int(v[1]))
            for k, v in (co.get("lifecycle_groups") or base.cohorts.lifecycle).items()}
    cohorts = CohortConfig(edges, life)

    o = raw.get("opportunities") or {}
    opp = OpportunityConfig(tuple(o.get("protective_services", base.opportunities.protective)),
                            tuple(o.get("streaming_services", base.opportunities.streaming)),
                            int(o.get("contract_review_min_tenure_months", 12)),
                            int(o.get("bundle_review_max_protective_services", 1)))

    f = raw.get("forecast") or {}
    fc = ForecastConfig(str(f.get("frequency", "M")), int(f.get("min_periods", 24)),
                        int(f.get("min_periods_for_seasonality", 36)), float(f.get("max_missing_period_share", 0.1)),
                        int(f.get("max_rows", 50_000)), int(f.get("backtest_holdout_periods", 6)))
    _need(fc.frequency == "M", "only monthly (M) frequency is supported")
    _need(fc.min_periods >= 12, "min_periods must be >= 12")
    _need(0 <= fc.max_missing_share < 1 and fc.max_rows > 0 and fc.holdout >= 1, "forecast settings invalid")

    a = raw.get("api") or {}
    api = ApiConfig(int(a.get("default_page_size", 25)), int(a.get("max_page_size", 200)))
    _need(1 <= api.default_page_size <= api.max_page_size, "api page sizes invalid")
    return RevenueConfig(data, quality, clv, risk, cohorts, opp, fc, api)


def load_config(path: str | Path | None) -> RevenueConfig:
    """Load YAML; a missing file yields documented defaults (so the package still runs when the file is absent)."""
    if path is None or not Path(path).is_file():
        return default_config()
    try:
        raw = yaml.safe_load(Path(path).read_text(encoding="utf-8")) or {}
    except yaml.YAMLError as exc:
        raise RevenueConfigError("configuration is not valid YAML") from exc
    return parse_config(raw)
