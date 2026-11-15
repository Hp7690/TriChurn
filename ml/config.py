"""YAML configuration loading. All thresholds and business-relevant constants live in configs/."""
from __future__ import annotations

import copy
from pathlib import Path
from typing import Any

import yaml

ROOT = Path(__file__).resolve().parents[1]
CONFIG_DIR = ROOT / "configs"


def load_yaml(path: str | Path) -> dict[str, Any]:
    with open(path, encoding="utf-8") as fh:
        return yaml.safe_load(fh) or {}


def deep_merge(base: dict[str, Any], override: dict[str, Any]) -> dict[str, Any]:
    out = copy.deepcopy(base)
    for key, value in override.items():
        if isinstance(value, dict) and isinstance(out.get(key), dict):
            out[key] = deep_merge(out[key], value)
        else:
            out[key] = copy.deepcopy(value)
    return out


def load_config(
    name: str, overrides: dict[str, Any] | None = None, config_dir: Path = CONFIG_DIR
) -> dict[str, Any]:
    cfg = load_yaml(Path(config_dir) / f"{name}.yaml")
    return deep_merge(cfg, overrides) if overrides else cfg
