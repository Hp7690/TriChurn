"""Parse and validate ``configs/business.yaml`` + ``configs/risk_bands.yaml`` into frozen typed config objects."""
from __future__ import annotations

from pathlib import Path
from typing import Any

from ml.business.schemas import (
    MODEL_THRESHOLD,
    NO_ACTION_ID,
    BusinessConfig,
    ClvConfig,
    CurrencyConfig,
    InterventionPolicy,
    RetentionAction,
    RiskBand,
    WhatIfDefaults,
)
from ml.business.validation import require_finite, require_non_negative, require_probability
from ml.config import CONFIG_DIR, load_config
from ml.errors import BusinessConfigError, BusinessInputError

CLV_METHODS = ("revenue_x_lifetime",)


def _need(section: dict, key: str, where: str) -> Any:
    if not isinstance(section, dict) or key not in section:
        raise BusinessConfigError(f"Business config is missing '{where}.{key}'.")
    return section[key]


def _flag(value: Any, name: str) -> bool:
    """A real YAML boolean. ``bool("false")`` is True, so strings/numbers must be rejected, not coerced."""
    if not isinstance(value, bool):
        raise BusinessConfigError(f"Invalid business config value: {name} must be true or false, got {value!r}.")
    return value


def _checked(fn, value: Any, name: str) -> float:
    try:
        return fn(value, name)
    except BusinessInputError as exc:
        raise BusinessConfigError(f"Invalid business config value: {exc}") from exc


def _parse_clv(raw: dict) -> ClvConfig:
    method = _need(raw, "method", "clv")
    if method not in CLV_METHODS:
        raise BusinessConfigError(f"clv.method must be one of {CLV_METHODS}, got {method!r}.")
    by_segment = _need(raw, "lifetime_months_by_segment", "clv") or {}
    if not isinstance(by_segment, dict):
        raise BusinessConfigError("clv.lifetime_months_by_segment must be a mapping.")
    cfg = ClvConfig(
        method=method,
        revenue_field=str(_need(raw, "revenue_field", "clv")),
        revenue_multiplier=_checked(require_non_negative, _need(raw, "revenue_multiplier", "clv"),
                                    "clv.revenue_multiplier"),
        gross_margin=_checked(require_probability, _need(raw, "gross_margin", "clv"), "clv.gross_margin"),
        monthly_discount_rate=_checked(require_non_negative, _need(raw, "monthly_discount_rate", "clv"),
                                       "clv.monthly_discount_rate"),
        lifetime_segment_field=str(_need(raw, "lifetime_segment_field", "clv")),
        lifetime_months_by_segment={str(k): _checked(require_non_negative, v, f"clv.lifetime_months_by_segment[{k}]")
                                    for k, v in by_segment.items()},
        default_lifetime_months=_checked(require_non_negative, _need(raw, "default_lifetime_months", "clv"),
                                         "clv.default_lifetime_months"),
        allow_default_lifetime=_flag(_need(raw, "allow_default_lifetime", "clv"), "clv.allow_default_lifetime"),
    )
    return cfg


def _parse_actions(raw: dict) -> dict[str, RetentionAction]:
    if not isinstance(raw, dict) or not raw:
        raise BusinessConfigError("Business config needs a non-empty 'actions' mapping.")
    out: dict[str, RetentionAction] = {}
    for action_id, a in raw.items():
        where = f"actions.{action_id}"
        if not isinstance(a, dict):
            raise BusinessConfigError(f"{where} must be a mapping (name, cost, success_rate, enabled, ...).")
        min_clv = a.get("min_clv")
        out[str(action_id)] = RetentionAction(
            action_id=str(action_id), name=str(_need(a, "name", where)),
            cost=_checked(require_non_negative, _need(a, "cost", where), f"{where}.cost"),
            success_rate=_checked(require_probability, _need(a, "success_rate", where), f"{where}.success_rate"),
            description=str(a.get("description", "")), enabled=_flag(_need(a, "enabled", where), f"{where}.enabled"),
            min_clv=None if min_clv is None else _checked(require_non_negative, min_clv, f"{where}.min_clv"))
    base = out.get(NO_ACTION_ID)
    if base is None:
        raise BusinessConfigError(f"The '{NO_ACTION_ID}' action is mandatory.")
    if not base.enabled or base.cost != 0 or base.success_rate != 0:
        raise BusinessConfigError(f"'{NO_ACTION_ID}' must be enabled with cost 0 and success_rate 0.")
    return out


def _parse_policy(raw: dict) -> InterventionPolicy:
    mcp = _need(raw, "min_churn_probability", "policy")
    if mcp != MODEL_THRESHOLD:
        mcp = _checked(require_probability, mcp, "policy.min_churn_probability")
    cap = raw.get("max_action_cost")
    return InterventionPolicy(
        min_churn_probability=mcp,
        min_customer_value=_checked(require_non_negative, _need(raw, "min_customer_value", "policy"),
                                    "policy.min_customer_value"),
        min_expected_net_benefit=_checked(require_finite, _need(raw, "min_expected_net_benefit", "policy"),
                                          "policy.min_expected_net_benefit"),
        max_action_cost=None if cap is None else _checked(require_non_negative, cap, "policy.max_action_cost"))


def _parse_bands(raw: dict) -> tuple[RiskBand, ...]:
    items = _need(raw, "bands", "risk_bands")
    if not isinstance(items, list) or not items:
        raise BusinessConfigError("risk_bands.bands must be a non-empty list.")
    bands = tuple(RiskBand(str(_need(b, "name", "risk_bands.bands")),
                           _checked(require_probability, _need(b, "min_probability", "risk_bands.bands"),
                                    "risk_bands.min_probability")) for b in items)
    mins = [b.min_probability for b in bands]
    if mins[0] != 0.0:
        raise BusinessConfigError("The first risk band must start at min_probability 0.")
    if any(b >= a for a, b in zip(mins[1:], mins[:-1], strict=False)) or len(set(b.name for b in bands)) != len(bands):
        raise BusinessConfigError("Risk bands need strictly increasing min_probability and unique names.")
    return bands


def _parse_what_if(raw: dict) -> WhatIfDefaults:
    sw = _need(_need(raw, "sweeps", "what_if"), "churn_probability", "what_if.sweeps")
    start, stop, step = (_checked(require_probability, sw[k], f"what_if.sweeps.churn_probability.{k}")
                         for k in ("start", "stop", "step"))
    if step <= 0 or start > stop:
        raise BusinessConfigError("what_if churn_probability sweep needs step > 0 and start <= stop.")

    def mults(key: str) -> tuple[float, ...]:
        vals = _need(raw["sweeps"], key, "what_if.sweeps")
        return tuple(_checked(require_non_negative, v, f"what_if.sweeps.{key}") for v in vals)

    return WhatIfDefaults((start, stop, step), mults("success_rate_multiplier"), mults("cost_multiplier"))


def parse_business_config(business: dict, risk_bands: dict) -> BusinessConfig:
    """Validate raw mappings (as loaded from YAML) into a ``BusinessConfig``."""
    cur = _need(business, "currency", "business")
    return BusinessConfig(
        currency=CurrencyConfig(str(_need(cur, "code", "currency")), str(_need(cur, "symbol", "currency"))),
        clv=_parse_clv(_need(business, "clv", "business")),
        actions=_parse_actions(_need(business, "actions", "business")),
        policy=_parse_policy(_need(business, "policy", "business")),
        risk_bands=_parse_bands(risk_bands),
        what_if=_parse_what_if(_need(business, "what_if", "business")))


def load_business_config(overrides: dict[str, Any] | None = None, config_dir: Path = CONFIG_DIR) -> BusinessConfig:
    """Load business.yaml + risk_bands.yaml; ``overrides`` are deep-merged into the business mapping."""
    business = load_config("business", overrides, config_dir)
    return parse_business_config(business, load_config("risk_bands", config_dir=config_dir))
