"""Phase 13: experience configuration loading and strict validation."""

from __future__ import annotations

from pathlib import Path

import pytest

from trichurn_experience.config import ExperienceConfigError, load_experience_config, parse_config

ROOT = Path(__file__).resolve().parents[2]


def test_shipped_config_loads_and_all_datasets_are_unconfigured():
    cfg = load_experience_config(ROOT / "configs" / "experience.yaml")
    assert cfg.enabled is True
    assert all(v is None for v in cfg.datasets.values()), "no real dataset may be configured by default"
    assert [g.name for g in cfg.lifecycle.groups] == [
        "New Customer",
        "Early Lifecycle",
        "Developing Customer",
        "Established Customer",
        "Long-Term Customer",
    ]
    assert cfg.lifecycle.groups[-1].max_months is None


def test_empty_config_uses_safe_defaults():
    cfg = parse_config({})
    assert cfg.enabled and cfg.limits.max_bytes == 5 * 1024 * 1024
    assert cfg.surveys.nps.promoter_min == 9 and cfg.surveys.csat.satisfied_min == 4


@pytest.mark.parametrize(
    "raw",
    [
        {"unknown_key": 1},
        {"limits": {"max_bytes": 0}},
        {"limits": {"max_rows": "many"}},
        {"limits": {"typo": 1}},
        {"enabled": "yes"},
        {"customer_id": {"pattern": "("}},
        {"timestamps": {"min_date": "not-a-date"}},
        {"datasets": {"feedback": 5}},
        {"datasets": {"surveys": "x.csv"}},
        {"lifecycle": {"groups": [{"name": "A", "min_months": 0, "max_months": 6}]}},  # < 2 groups
        {
            "lifecycle": {
                "groups": [
                    {"name": "A", "min_months": 1, "max_months": 6},
                    {"name": "B", "min_months": 6, "max_months": None},
                ]
            }
        },  # not from 0
        {
            "lifecycle": {
                "groups": [
                    {"name": "A", "min_months": 0, "max_months": 6},
                    {"name": "B", "min_months": 7, "max_months": None},
                ]
            }
        },  # gap
        {
            "lifecycle": {
                "groups": [
                    {"name": "A", "min_months": 0, "max_months": 6},
                    {"name": "B", "min_months": 6, "max_months": 12},
                ]
            }
        },  # last not open
        {
            "lifecycle": {
                "groups": [
                    {"name": "A", "min_months": 0, "max_months": None},
                    {"name": "B", "min_months": 6, "max_months": None},
                ]
            }
        },  # open in middle
        {
            "lifecycle": {
                "groups": [
                    {"name": "A", "min_months": 0, "max_months": 6},
                    {"name": "A", "min_months": 6, "max_months": None},
                ]
            }
        },  # duplicate name
        {"lifecycle": {"risk_bands": {"low_max": 0.6, "medium_max": 0.5}}},
        {"surveys": {"nps": {"scale_min": 0, "scale_max": 10, "detractor_max": 9, "promoter_min": 9}}},
        {"surveys": {"csat": {"scale_min": 1, "scale_max": 5, "satisfied_min": 9}}},
        {"surveys": {"nps": {"typo": 1}}},
        {"complaints": {"resolved_statuses": ["gone"]}},
        {"complaints": {"severities": []}},
        {"sentiment": {"labels": ["only-one"]}},
    ],
)
def test_invalid_config_is_rejected(raw):
    with pytest.raises(ExperienceConfigError):
        parse_config(raw)


def test_custom_groups_are_accepted():
    cfg = parse_config(
        {
            "lifecycle": {
                "groups": [
                    {"name": "Young", "min_months": 0, "max_months": 10},
                    {"name": "Old", "min_months": 10, "max_months": None},
                ]
            }
        }
    )
    assert [g.name for g in cfg.lifecycle.groups] == ["Young", "Old"]


def test_missing_and_malformed_files_raise_without_leaking_paths(tmp_path):
    with pytest.raises(ExperienceConfigError) as missing:
        load_experience_config(tmp_path / "nope.yaml")
    assert str(tmp_path) not in str(missing.value)
    bad = tmp_path / "bad.yaml"
    bad.write_text("a: [unclosed", encoding="utf-8")
    with pytest.raises(ExperienceConfigError) as malformed:
        load_experience_config(bad)
    assert str(tmp_path) not in str(malformed.value)


def test_yaml_cannot_construct_python_objects(tmp_path):
    evil = tmp_path / "evil.yaml"
    evil.write_text("enabled: !!python/object/apply:os.system ['echo hacked']\n", encoding="utf-8")
    with pytest.raises(ExperienceConfigError):
        load_experience_config(evil)
