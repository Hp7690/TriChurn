"""Customer lifetime value: observed billing proxy + configurable scenario estimate.

* observed_billing  = TotalCharges (valid only)              -> ACTUAL billing, PROXY for realised value
* forward_value     = MonthlyCharges x annuity(H, r)         -> ILLUSTRATIVE until assumptions are confirmed
* estimated_clv     = observed_billing + forward_value
* probability_adjusted_clv = observed_billing + forward_value x (1 - p)   (VALIDATED_OUT_OF_SAMPLE p only)
Revenue is never called profit. Already-churned customers have forward value 0. Unknown inputs give NaN, never 0.
"""
from __future__ import annotations

import numpy as np
import pandas as pd

from ..analytics.config import ClvConfig
from ..analytics.dataset import usable_probabilities
from ..availability import MetricStatus


def annuity_factor(months: float, monthly_rate: float) -> float:
    """sum_{t=1..H} (1+r)^-t ; equals H when r == 0."""
    if months <= 0:
        return 0.0
    if monthly_rate == 0:
        return float(months)
    return float((1 - (1 + monthly_rate) ** (-months)) / monthly_rate)


def scenario_status(cfg: ClvConfig) -> MetricStatus:
    if not cfg.scenario_enabled or not cfg.remaining_months:
        return MetricStatus.UNAVAILABLE
    return MetricStatus.ESTIMATED if cfg.assumptions_confirmed else MetricStatus.ILLUSTRATIVE


def add_clv_columns(df: pd.DataFrame, cfg: ClvConfig) -> pd.DataFrame:
    out = df.copy()
    out["forward_value"] = np.nan
    out["estimated_clv"] = np.nan
    out["probability_adjusted_clv"] = np.nan
    if scenario_status(cfg) is MetricStatus.UNAVAILABLE or "Contract" not in out.columns:
        return out
    factors = {k: annuity_factor(v, cfg.monthly_discount_rate) for k, v in cfg.remaining_months.items()}
    f = out["Contract"].map(factors)
    churned = out["churned"]
    forward = out["monthly"] * f
    forward = forward.where(churned != True, 0.0)           # noqa: E712 - already churned: nothing forward
    forward = forward.where(churned.isin([True, False]))    # churn unknown: unavailable
    out["forward_value"] = forward.astype(float)
    out["estimated_clv"] = (out["billing"] + out["forward_value"]).astype(float)
    p = usable_probabilities(out)
    if p is not None:
        adj = out["billing"] + out["forward_value"] * (1 - p)
        out["probability_adjusted_clv"] = adj.astype(float)
    return out


def mean_or_none(s: pd.Series) -> float | None:
    s = s.dropna()
    return None if s.empty else float(s.mean())


def sum_or_none(s: pd.Series) -> float | None:
    s = s.dropna()
    return None if s.empty else float(s.sum())


def distribution(values: pd.Series, bins: int = 10) -> list[dict]:
    """Equal-width histogram of valid values (no imputation). Empty when nothing is valid."""
    v = values.dropna()
    if v.empty:
        return []
    top = float(v.max())
    if top <= 0:
        return [{"lower": 0.0, "upper": 0.0, "count": int(len(v))}]
    edges = np.linspace(0, top, bins + 1)
    counts, _ = np.histogram(v, bins=edges)
    return [{"lower": round(float(edges[i]), 2), "upper": round(float(edges[i + 1]), 2), "count": int(counts[i])}
            for i in range(bins)]
