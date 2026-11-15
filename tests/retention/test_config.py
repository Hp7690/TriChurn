from __future__ import annotations

import copy

import pytest
import yaml

from retention.config import DEFAULT_CONFIG_PATH, load_retention_config, parse_config
from retention.errors import RetentionInputError


def _raw():
    return yaml.safe_load(DEFAULT_CONFIG_PATH.read_text(encoding="utf-8"))


def test_shipped_config_loads_and_weights_sum_to_one():
    cfg = load_retention_config()
    p = cfg.priority
    assert abs(p.weight_value_at_risk + p.weight_churn_probability + p.weight_expected_net_benefit - 1.0) < 1e-9
    assert p.tier_min_scores == (95.0, 90.0, 80.0)
    assert cfg.simulator.max_scenarios >= 1


def test_config_defines_no_action_costs_or_success_rates():
    text = DEFAULT_CONFIG_PATH.read_text(encoding="utf-8")
    assert "success_rate:" not in text and "cost:" not in text      # Phase 4 business.yaml stays the single source


@pytest.mark.parametrize("mutate", [
    lambda r: r["priority"]["weights"].update(value_at_risk=0.9),
    lambda r: r["priority"].update(tier_min_scores=[60, 80, 40]),
    lambda r: r["priority"].update(tier_min_scores=[90, 80]),
    lambda r: r["priority"]["weights"].update(churn_probability="0.3"),
    lambda r: r["simulator"].update(max_scenarios=0),
    lambda r: r["uplift_readiness"].update(require_randomized_assignment="yes"),
    lambda r: r["uplift_readiness"].update(min_outcome_coverage=1.5),
    lambda r: r.pop("campaigns"),
])
def test_invalid_config_is_rejected(mutate):
    raw = copy.deepcopy(_raw())
    mutate(raw)
    with pytest.raises(RetentionInputError):
        parse_config(raw)


def test_unreadable_config_raises_safe_error(tmp_path):
    with pytest.raises(RetentionInputError) as exc:
        load_retention_config(tmp_path / "missing.yaml")
    assert str(tmp_path) not in str(exc.value)
