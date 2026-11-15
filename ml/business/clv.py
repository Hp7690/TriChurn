"""Customer lifetime value: a transparent, deterministic BASELINE, not a causal or learned lifetime model.

    CLV = revenue_multiplier * gross_margin * monthly_revenue * discounted_months(L, d)

    discounted_months(L, d) = L                          if d == 0
                            = (1 - (1 + d) ** -L) / d    otherwise   (= sum over months t=1..L of (1+d)^-t)

``L`` is an ASSUMED remaining lifetime in months looked up from the customer's segment (e.g. contract type) in
``configs/business.yaml``; a configured default is used only when allowed. Nothing here is estimated from data
and nothing is invented: a missing revenue value raises.
"""
from __future__ import annotations

import math
import numbers
from collections.abc import Mapping
from typing import Any

import pandas as pd

from ml.business.schemas import ClvConfig, ClvResult
from ml.business.validation import require_non_negative
from ml.errors import BusinessInputError


def _is_missing(value: Any) -> bool:
    if value is None or value is pd.NA:
        return True
    if isinstance(value, numbers.Real) and not isinstance(value, bool) and math.isnan(value):
        return True
    return isinstance(value, str) and not value.strip()


def discounted_months(lifetime_months: float, monthly_discount_rate: float) -> float:
    """Present-value months: the lifetime itself when undiscounted, else the closed-form annuity factor."""
    if monthly_discount_rate == 0.0:
        return lifetime_months
    return (1.0 - (1.0 + monthly_discount_rate) ** -lifetime_months) / monthly_discount_rate


def resolve_lifetime(segment_value: Any, cfg: ClvConfig) -> tuple[float, str]:
    """Assumed remaining months for the customer's segment, and where the number came from."""
    key = None if _is_missing(segment_value) else str(segment_value).strip()
    if key is not None and key in cfg.lifetime_months_by_segment:
        return cfg.lifetime_months_by_segment[key], f"segment:{key}"
    if not cfg.allow_default_lifetime:
        raise BusinessInputError(
            f"No configured lifetime for {cfg.lifetime_segment_field}={segment_value!r} and "
            "clv.allow_default_lifetime is false.")
    return cfg.default_lifetime_months, "default"


def compute_clv(monthly_revenue: Any, segment_value: Any, cfg: ClvConfig) -> ClvResult:
    """CLV for one customer from monthly revenue (source units) and a segment value."""
    if _is_missing(monthly_revenue):
        raise BusinessInputError(f"{cfg.revenue_field} is required to compute CLV and is missing; it is not guessed.")
    revenue = require_non_negative(monthly_revenue, cfg.revenue_field)
    months, source = resolve_lifetime(segment_value, cfg)
    pv_months = discounted_months(months, cfg.monthly_discount_rate)
    clv = cfg.revenue_multiplier * cfg.gross_margin * revenue * pv_months
    return ClvResult(clv=clv, monthly_revenue=cfg.revenue_multiplier * revenue, lifetime_months=months,
                     lifetime_source=source, gross_margin=cfg.gross_margin,
                     monthly_discount_rate=cfg.monthly_discount_rate, discounted_months=pv_months)


def compute_clv_for_record(record: Mapping[str, Any], cfg: ClvConfig) -> ClvResult:
    """Read the configured revenue and segment fields from a raw customer record."""
    if cfg.revenue_field not in record:
        raise BusinessInputError(f"Customer record has no '{cfg.revenue_field}' column; CLV cannot be computed.")
    return compute_clv(record[cfg.revenue_field], record.get(cfg.lifetime_segment_field), cfg)
