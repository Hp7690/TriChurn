"""Load and strictly validate ``configs/retention.yaml``."""
from __future__ import annotations

import math
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import yaml

from retention.errors import RetentionInputError

DEFAULT_CONFIG_PATH = Path(__file__).resolve().parents[1] / "configs" / "retention.yaml"


@dataclass(frozen=True)
class PriorityConfig:
    weight_value_at_risk: float
    weight_churn_probability: float
    weight_expected_net_benefit: float
    tier_min_scores: tuple[float, float, float]


@dataclass(frozen=True)
class SimulatorConfig:
    max_scenarios: int
    max_target_customers: int


@dataclass(frozen=True)
class CampaignConfig:
    max_customers_per_request: int


@dataclass(frozen=True)
class UpliftReadinessConfig:
    min_customers_per_arm: int
    min_outcome_coverage: float
    require_randomized_assignment: bool


@dataclass(frozen=True)
class RetentionConfig:
    priority: PriorityConfig
    simulator: SimulatorConfig
    campaigns: CampaignConfig
    uplift: UpliftReadinessConfig


def _need(section: Any, key: str, where: str) -> Any:
    if not isinstance(section, dict) or key not in section:
        raise RetentionInputError(f"Retention config is missing '{where}.{key}'.")
    return section[key]


def _number(value: Any, name: str, low: float | None = None, high: float | None = None) -> float:
    if isinstance(value, bool) or not isinstance(value, int | float) or not math.isfinite(value):
        raise RetentionInputError(f"Retention config value {name} must be a finite number.")
    if (low is not None and value < low) or (high is not None and value > high):
        raise RetentionInputError(f"Retention config value {name} is out of range.")
    return float(value)


def _integer(value: Any, name: str, low: int) -> int:
    if isinstance(value, bool) or not isinstance(value, int) or value < low:
        raise RetentionInputError(f"Retention config value {name} must be an integer >= {low}.")
    return value


def parse_config(raw: dict[str, Any]) -> RetentionConfig:
    pri = _need(raw, "priority", "retention")
    w = _need(pri, "weights", "priority")
    weights = [_number(_need(w, k, "priority.weights"), f"priority.weights.{k}", 0.0, 1.0)
               for k in ("value_at_risk", "churn_probability", "expected_net_benefit")]
    if not math.isclose(sum(weights), 1.0, abs_tol=1e-9):
        raise RetentionInputError("Retention config priority.weights must sum to 1.")
    tiers = _need(pri, "tier_min_scores", "priority")
    if not isinstance(tiers, list) or len(tiers) != 3:
        raise RetentionInputError("Retention config priority.tier_min_scores must list exactly three scores.")
    cuts = tuple(_number(t, "priority.tier_min_scores", 0.0, 100.0) for t in tiers)
    if not cuts[0] > cuts[1] > cuts[2]:
        raise RetentionInputError("Retention config priority.tier_min_scores must be strictly decreasing.")
    sim, camp, up = (_need(raw, k, "retention") for k in ("simulator", "campaigns", "uplift_readiness"))
    return RetentionConfig(
        PriorityConfig(weights[0], weights[1], weights[2], cuts),  # type: ignore[arg-type]
        SimulatorConfig(_integer(_need(sim, "max_scenarios", "simulator"), "simulator.max_scenarios", 1),
                        _integer(_need(sim, "max_target_customers", "simulator"),
                                 "simulator.max_target_customers", 1)),
        CampaignConfig(_integer(_need(camp, "max_customers_per_request", "campaigns"),
                                "campaigns.max_customers_per_request", 1)),
        UpliftReadinessConfig(
            _integer(_need(up, "min_customers_per_arm", "uplift_readiness"), "uplift.min_customers_per_arm", 1),
            _number(_need(up, "min_outcome_coverage", "uplift_readiness"), "uplift.min_outcome_coverage", 0.0, 1.0),
            _flag(_need(up, "require_randomized_assignment", "uplift_readiness"))))


def _flag(value: Any) -> bool:
    if not isinstance(value, bool):
        raise RetentionInputError("Retention config flags must be true or false.")
    return value


def load_retention_config(path: str | Path | None = None) -> RetentionConfig:
    target = Path(path) if path is not None else DEFAULT_CONFIG_PATH
    try:
        raw = yaml.safe_load(target.read_text(encoding="utf-8"))
    except (OSError, yaml.YAMLError) as exc:
        raise RetentionInputError("The retention configuration could not be read.") from exc
    return parse_config(raw if isinstance(raw, dict) else {})
