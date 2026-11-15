"""Load and strictly validate ``configs/autonomy.yaml``."""
from __future__ import annotations

import math
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import yaml

from autonomy.errors import AutonomyInputError

DEFAULT_CONFIG_PATH = Path(__file__).resolve().parents[1] / "configs" / "autonomy.yaml"
RISK_ORDER = ("LOW", "MEDIUM", "HIGH", "CRITICAL")


@dataclass(frozen=True)
class AutonomyConfig:
    agent_enabled: bool
    rules_version: str
    max_recommendations_per_request: int
    action_categories: dict[str, str]
    evidence_risk_bands: tuple[str, ...]
    subscription_review_max_tenure: int
    monitoring_enabled: bool
    min_probability_change: float
    approvals_enabled: bool
    note_max_length: int
    learning_enabled: bool
    min_validated_outcomes: int
    min_outcomes_per_action: int
    default_page_size: int
    max_page_size: int


def _section(raw: Any, key: str) -> dict[str, Any]:
    value = raw.get(key) if isinstance(raw, dict) else None
    if not isinstance(value, dict):
        raise AutonomyInputError(f"Autonomy config is missing section '{key}'.")
    return value


def _flag(section: dict[str, Any], key: str) -> bool:
    value = section.get(key)
    if not isinstance(value, bool):
        raise AutonomyInputError(f"Autonomy config value '{key}' must be true or false.")
    return value


def _int(section: dict[str, Any], key: str, low: int) -> int:
    value = section.get(key)
    if isinstance(value, bool) or not isinstance(value, int) or value < low:
        raise AutonomyInputError(f"Autonomy config value '{key}' must be an integer >= {low}.")
    return value


def parse_config(raw: Any) -> AutonomyConfig:
    agent, monitoring = _section(raw, "agent"), _section(raw, "monitoring")
    workflow, learning, paging = _section(raw, "workflow"), _section(raw, "learning"), _section(raw, "pagination")
    version = agent.get("rules_version")
    if not isinstance(version, str) or not version.strip():
        raise AutonomyInputError("Autonomy config value 'rules_version' is required.")
    categories = agent.get("action_categories")
    if not isinstance(categories, dict) or not all(isinstance(k, str) and isinstance(v, str)
                                                    for k, v in categories.items()):
        raise AutonomyInputError("Autonomy config 'action_categories' must map action ids to category names.")
    bands = agent.get("risk_bands_for_evidence_rules")
    if not isinstance(bands, list) or not bands or any(b not in RISK_ORDER for b in bands):
        raise AutonomyInputError("Autonomy config risk bands must be a non-empty list of known bands.")
    change = monitoring.get("min_probability_change")
    if isinstance(change, bool) or not isinstance(change, int | float) or not math.isfinite(change) \
            or not 0.0 < change <= 1.0:
        raise AutonomyInputError("Autonomy config 'min_probability_change' must be in (0, 1].")
    default_size, max_size = _int(paging, "default_page_size", 1), _int(paging, "max_page_size", 1)
    if default_size > max_size:
        raise AutonomyInputError("Autonomy config default_page_size cannot exceed max_page_size.")
    return AutonomyConfig(
        agent_enabled=_flag(agent, "enabled"), rules_version=version.strip(),
        max_recommendations_per_request=_int(agent, "max_recommendations_per_request", 1),
        action_categories=dict(categories), evidence_risk_bands=tuple(bands),
        subscription_review_max_tenure=_int(agent, "subscription_review_max_tenure_months", 0),
        monitoring_enabled=_flag(monitoring, "enabled"), min_probability_change=float(change),
        approvals_enabled=_flag(workflow, "approvals_enabled"), note_max_length=_int(workflow, "note_max_length", 1),
        learning_enabled=_flag(learning, "enabled"),
        min_validated_outcomes=_int(learning, "min_validated_outcomes", 1),
        min_outcomes_per_action=_int(learning, "min_outcomes_per_action", 1),
        default_page_size=default_size, max_page_size=max_size)


def load_autonomy_config(path: str | Path | None = None) -> AutonomyConfig:
    target = Path(path) if path is not None else DEFAULT_CONFIG_PATH
    try:
        raw = yaml.safe_load(target.read_text(encoding="utf-8"))
    except (OSError, yaml.YAMLError) as exc:
        raise AutonomyInputError("The autonomy configuration could not be read.") from exc
    return parse_config(raw)
