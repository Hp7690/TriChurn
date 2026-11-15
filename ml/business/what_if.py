"""SIMULATION / WHAT-IF engine.

Re-computes ENB, the decision and the recommended action under changed ASSUMPTIONS. It never retrains or touches the
model, the dataset or the stored configuration: the supplied ``BusinessConfig`` is frozen and every override is
applied to a copy. Results are estimates under assumptions and say nothing about causal treatment effects.
"""
from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass, field, replace
from typing import Any

import numpy as np

from ml.business.decision import decide, resolve_policy
from ml.business.retention import best_by_enb
from ml.business.risk_bands import assign_risk_band
from ml.business.schemas import (
    NO_ACTION_ID,
    NON_CAUSAL_NOTE,
    SIMULATION_LABEL,
    BusinessConfig,
    DecisionResult,
    EnbBreakdown,
)
from ml.business.validation import require_non_negative, require_probability, require_rate
from ml.errors import BusinessInputError


@dataclass(frozen=True)
class Scenario:
    """Assumption overrides. ``None`` / empty means 'keep the baseline value'."""
    churn_probability: float | None = None
    clv: float | None = None
    action_cost: Mapping[str, float] = field(default_factory=dict)
    action_success_rate: Mapping[str, float] = field(default_factory=dict)
    min_churn_probability: float | None = None
    min_customer_value: float | None = None
    min_expected_net_benefit: float | None = None

    def changed(self) -> dict[str, Any]:
        return {k: v for k, v in self.__dict__.items() if v not in (None, {})}


@dataclass(frozen=True)
class Outcome:
    churn_probability: float
    clv: float
    risk_band: str
    decision: DecisionResult
    economics: EnbBreakdown      # best eligible action by ENB, even if negative / policy-blocked (else no_action)
    economics_action_id: str

    def to_dict(self) -> dict[str, Any]:
        return {"churn_probability": self.churn_probability, "clv": self.clv, "risk_band": self.risk_band,
                "decision": self.decision.decision,
                "recommended_action_id": self.decision.recommended.action.action_id,
                "best_eligible_action_id": None if self.decision.best_eligible is None
                else self.decision.best_eligible.action.action_id,
                "economics_action_id": self.economics_action_id, "economics": self.economics.to_dict(),
                "reasons": [r.to_dict() for r in self.decision.reasons]}


@dataclass(frozen=True)
class WhatIfResult:
    label: str
    note: str
    assumptions_changed: dict[str, Any]
    baseline: Outcome
    scenario: Outcome
    delta: dict[str, Any]

    def to_dict(self) -> dict[str, Any]:
        return {"label": self.label, "note": self.note, "assumptions_changed": self.assumptions_changed,
                "baseline": self.baseline.to_dict(), "scenario": self.scenario.to_dict(), "delta": self.delta}


def _outcome(config: BusinessConfig, p: float, clv: float, model_threshold: float | None) -> Outcome:
    result = decide(clv, p, config.actions, resolve_policy(config.policy, model_threshold))
    shown = best_by_enb(result.evaluations) or result.recommended
    return Outcome(p, clv, assign_risk_band(p, config.risk_bands), result, shown.enb, shown.action.action_id)


def _override_actions(config: BusinessConfig, scenario: Scenario) -> BusinessConfig:
    unknown = (set(scenario.action_cost) | set(scenario.action_success_rate)) - set(config.actions)
    if unknown:
        raise BusinessInputError(f"Scenario refers to unknown actions: {sorted(unknown)}.")
    if NO_ACTION_ID in scenario.action_cost or NO_ACTION_ID in scenario.action_success_rate:
        raise BusinessInputError(f"'{NO_ACTION_ID}' must keep cost 0 and success_rate 0 and cannot be overridden.")
    actions = dict(config.actions)
    for aid, cost in scenario.action_cost.items():
        actions[aid] = replace(actions[aid], cost=require_non_negative(cost, f"scenario cost[{aid}]"))
    for aid, rate in scenario.action_success_rate.items():
        actions[aid] = replace(actions[aid], success_rate=require_rate(rate, f"scenario success_rate[{aid}]"))
    return replace(config, actions=actions)


def _override_policy(config: BusinessConfig, scenario: Scenario) -> BusinessConfig:
    pol = config.policy
    if scenario.min_churn_probability is not None:
        pol = replace(pol, min_churn_probability=require_probability(scenario.min_churn_probability,
                                                                     "scenario min_churn_probability"))
    if scenario.min_customer_value is not None:
        pol = replace(pol, min_customer_value=require_non_negative(scenario.min_customer_value,
                                                                   "scenario min_customer_value"))
    if scenario.min_expected_net_benefit is not None:
        pol = replace(pol, min_expected_net_benefit=float(scenario.min_expected_net_benefit))
    return replace(config, policy=pol)


def simulate(config: BusinessConfig, churn_probability: Any, clv: Any, scenario: Scenario,
             model_threshold: float | None = None) -> WhatIfResult:
    """Baseline vs scenario for one customer. ``config`` is not modified."""
    p0, clv0 = require_probability(churn_probability), require_non_negative(clv, "clv")
    p1 = p0 if scenario.churn_probability is None else require_probability(scenario.churn_probability,
                                                                           "scenario churn_probability")
    clv1 = clv0 if scenario.clv is None else require_non_negative(scenario.clv, "scenario clv")
    scen_cfg = _override_policy(_override_actions(config, scenario), scenario)
    base, scen = _outcome(config, p0, clv0, model_threshold), _outcome(scen_cfg, p1, clv1, model_threshold)
    b, s = base.economics, scen.economics
    delta = {"expected_benefit": s.expected_benefit - b.expected_benefit,
             "expected_cost": s.expected_cost - b.expected_cost,
             "expected_net_benefit": s.expected_net_benefit - b.expected_net_benefit,
             "decision_changed": base.decision.decision != scen.decision.decision,
             "recommended_action_changed": base.decision.recommended.action.action_id
             != scen.decision.recommended.action.action_id}
    return WhatIfResult(SIMULATION_LABEL, NON_CAUSAL_NOTE, scenario.changed(), base, scen, delta)


def sweep_churn_probability(config: BusinessConfig, clv: float, model_threshold: float | None = None,
                            points: list[float] | None = None) -> list[dict[str, Any]]:
    """Decision and best-action economics across a probability grid (default: ``what_if.sweeps`` in config)."""
    start, stop, step = config.what_if.probability_sweep
    grid = points if points is not None else [round(float(x), 10) for x in np.arange(start, stop + step / 2, step)]
    rows = []
    for p in grid:
        o = _outcome(config, require_probability(p), require_non_negative(clv, "clv"), model_threshold)
        rows.append({"churn_probability": p, "decision": o.decision.decision,
                     "recommended_action_id": o.decision.recommended.action.action_id,
                     "expected_net_benefit": o.economics.expected_net_benefit})
    return rows


def sweep_multiplier(config: BusinessConfig, churn_probability: float, clv: float, kind: str,
                     model_threshold: float | None = None, multipliers: tuple[float, ...] | None = None
                     ) -> list[dict[str, Any]]:
    """Scale every non-zero success rate (``kind='success_rate'``, capped at 1) or cost (``kind='cost'``)."""
    if kind not in ("success_rate", "cost"):
        raise BusinessInputError("kind must be 'success_rate' or 'cost'.")
    mults = multipliers or (config.what_if.success_rate_multipliers if kind == "success_rate"
                            else config.what_if.cost_multipliers)
    rows = []
    for mult in mults:
        mult = require_non_negative(mult, "multiplier")
        others = {a: x for a, x in config.actions.items() if a != NO_ACTION_ID}
        sc = Scenario(
            action_success_rate={a: min(1.0, x.success_rate * mult) for a, x in others.items()}
            if kind == "success_rate" else {},
            action_cost={a: x.cost * mult for a, x in others.items()} if kind == "cost" else {})
        r = simulate(config, churn_probability, clv, sc, model_threshold)
        rows.append({"multiplier": mult, "decision": r.scenario.decision.decision,
                     "recommended_action_id": r.scenario.decision.recommended.action.action_id,
                     "expected_net_benefit": r.scenario.economics.expected_net_benefit})
    return rows
