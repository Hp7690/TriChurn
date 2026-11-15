"""Runtime settings for the API layer.

Everything is driven by ``TRICHURN_*`` environment variables with safe defaults. No secrets, no machine-specific
absolute paths: relative paths are resolved against the project root (the directory that contains ``app/``).
"""
from __future__ import annotations

import os
import re
from collections.abc import Mapping
from dataclasses import dataclass, field
from pathlib import Path

API_VERSION = "v1"
API_PREFIX = "/api/v1"
SERVICE_NAME = "trichurn-api"

ENV_PREFIX = "TRICHURN_"
ENVIRONMENTS = ("production", "development", "test")

# ---- locked Phase 1-5 facts (see docs/phase6.md): the Phase 2 digest is pinned; Phase 5 uses its own sidecar.
LOCKED_PHASE2_SHA256 = "db399a55f650c6681e1caaf52257f909777e2c5fada3af5911370ddf5b8ff1ad"
DEFAULT_PHASE2_MODEL = "models/trichurn_churn_model_v2.0.0.joblib"
DEFAULT_PHASE5_MODEL = "models/trichurn_segmentation_v5.0.0.joblib"
DEFAULT_DATASET_CSV = "ml/data/raw/telco_churn.csv"
DEFAULT_DATASET_SPEC = "configs/datasets/telco.yaml"
LOCKED_SEGMENTATION_K = 3
LOCKED_SEGMENTATION_SEED = 42
LOCKED_SEGMENTATION_FEATURES = ("tenure", "MonthlyCharges", "TotalCharges", "service_count", "contract_risk")

_SHA256 = re.compile(r"^[0-9a-f]{64}$")
DISABLED = "disabled"


class ConfigurationError(ValueError):
    """A TRICHURN_* setting is malformed. Messages never echo the offending value."""


def default_project_root() -> Path:
    """The directory containing ``app/`` (i.e. the TriChurn project root after the overlay is merged)."""
    return Path(__file__).resolve().parents[2]


def _parse_bool(raw: str, name: str) -> bool:
    if raw not in ("true", "false"):          # never bool("false"): strings must be exactly true/false
        raise ConfigurationError(f"{name} must be 'true' or 'false'.")
    return raw == "true"


def _parse_sha(raw: str, name: str) -> str | None:
    value = raw.strip().lower()
    if value == DISABLED:
        return None
    if not _SHA256.match(value):
        raise ConfigurationError(f"{name} must be a 64-character lowercase hex SHA-256 or '{DISABLED}'.")
    return value


@dataclass(frozen=True)
class Settings:
    environment: str = "production"
    project_root: Path = field(default_factory=default_project_root)
    phase2_model_path: str = DEFAULT_PHASE2_MODEL
    phase2_expected_sha256: str | None = LOCKED_PHASE2_SHA256
    phase5_model_path: str = DEFAULT_PHASE5_MODEL
    phase5_expected_sha256: str | None = None          # None: integrity is checked against the artifact's own sidecar
    dataset_csv_path: str = DEFAULT_DATASET_CSV        # Phase 3 needs the TRAIN CSV to rebuild its SHAP background
    dataset_spec_path: str = DEFAULT_DATASET_SPEC
    expected_segmentation_k: int | None = LOCKED_SEGMENTATION_K
    expected_segmentation_seed: int | None = LOCKED_SEGMENTATION_SEED
    expected_segmentation_features: tuple[str, ...] | None = LOCKED_SEGMENTATION_FEATURES
    adapter_factory: str | None = None      # "package.module:callable" -> custom Phase15Port (INTEGRATION.md)
    enable_docs: bool = True

    def __post_init__(self) -> None:
        if self.environment not in ENVIRONMENTS:
            raise ConfigurationError(f"environment must be one of {ENVIRONMENTS}.")

    def resolve(self, path: str | Path) -> Path:
        """Absolute paths are kept; relative paths are anchored at the project root (never at the CWD)."""
        p = Path(path)
        return p if p.is_absolute() else self.project_root / p

    @classmethod
    def from_env(cls, env: Mapping[str, str] | None = None) -> Settings:
        e = os.environ if env is None else env
        get = lambda name: e.get(ENV_PREFIX + name)  # noqa: E731
        kwargs: dict[str, object] = {}
        for attr, name in (("environment", "ENVIRONMENT"), ("phase2_model_path", "PHASE2_MODEL"),
                           ("phase5_model_path", "PHASE5_MODEL"), ("dataset_csv_path", "DATASET_CSV"),
                           ("dataset_spec_path", "DATASET_SPEC"), ("adapter_factory", "ADAPTER_FACTORY")):
            if get(name) is not None:
                kwargs[attr] = get(name)
        if get("PROJECT_ROOT") is not None:
            kwargs["project_root"] = Path(get("PROJECT_ROOT"))
        if get("PHASE2_SHA256") is not None:
            kwargs["phase2_expected_sha256"] = _parse_sha(get("PHASE2_SHA256"), ENV_PREFIX + "PHASE2_SHA256")
        if get("PHASE5_SHA256") is not None:
            kwargs["phase5_expected_sha256"] = _parse_sha(get("PHASE5_SHA256"), ENV_PREFIX + "PHASE5_SHA256")
        if get("ENABLE_DOCS") is not None:
            kwargs["enable_docs"] = _parse_bool(get("ENABLE_DOCS"), ENV_PREFIX + "ENABLE_DOCS")
        return cls(**kwargs)  # type: ignore[arg-type]
