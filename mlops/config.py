
"""Phase 8 configuration: environment variables with safe, machine-independent defaults. No secrets.

Variables (all optional):
    MLFLOW_TRACKING_URI        default: local SQLite store under <project>/mlflow_local/
    MLFLOW_ARTIFACT_LOCATION   default: <project>/mlflow_local/artifacts   (used when the experiment is created)
    MLFLOW_EXPERIMENT_NAME     default: TriChurn-Churn-Prediction
    MLFLOW_MODEL_NAME          default: TriChurn-Churn-Model
    MLFLOW_MODEL_VERSION       default: 2.0.0          (semantic version of the locked Phase 2 model)
    TRICHURN_MODEL_PATH        default: models/trichurn_churn_model_v2.0.0.joblib   (relative -> project root)
    TRICHURN_MODEL_SHA256      default: the locked Phase 2 digest; 64 lowercase hex (or 'disabled' is NOT accepted:
                               the digest pin cannot be switched off in Phase 8)
"""
from __future__ import annotations

import os
import re
from collections.abc import Mapping
from dataclasses import dataclass, field
from pathlib import Path

from mlops.errors import MlopsConfigurationError

LOCKED_PHASE2_SHA256 = "db399a55f650c6681e1caaf52257f909777e2c5fada3af5911370ddf5b8ff1ad"
DEFAULT_MODEL_PATH = "models/trichurn_churn_model_v2.0.0.joblib"
DEFAULT_EXPERIMENT = "TriChurn-Churn-Prediction"
DEFAULT_MODEL_NAME = "TriChurn-Churn-Model"
DEFAULT_MODEL_VERSION = "2.0.0"
PRODUCTION_ALIAS = "production"
LOCAL_STORE_DIR = "mlflow_local"

_SHA256 = re.compile(r"^[0-9a-f]{64}$")
_SEMVER = re.compile(r"^\d+\.\d+\.\d+$")
_NAME = re.compile(r"^[A-Za-z0-9][A-Za-z0-9_.\- ]{0,127}$")


def default_project_root() -> Path:
    """The directory that contains ``mlops/`` (the TriChurn project root)."""
    return Path(__file__).resolve().parents[1]


def _check_name(value: str, name: str) -> str:
    if not _NAME.match(value):
        raise MlopsConfigurationError(f"{name} must be 1-128 characters: letters, digits, space, '_', '.', '-'.")
    return value


@dataclass(frozen=True)
class MlopsSettings:
    project_root: Path = field(default_factory=default_project_root)
    tracking_uri: str | None = None            # None -> local SQLite store (see ``effective_tracking_uri``)
    artifact_location: str | None = None       # None -> <root>/mlflow_local/artifacts
    experiment_name: str = DEFAULT_EXPERIMENT
    model_name: str = DEFAULT_MODEL_NAME
    model_version: str = DEFAULT_MODEL_VERSION
    model_path: str = DEFAULT_MODEL_PATH
    model_sha256: str = LOCKED_PHASE2_SHA256
    tracking_configured: bool = False          # True only when MLFLOW_TRACKING_URI was explicitly provided

    def __post_init__(self) -> None:
        object.__setattr__(
            self,
            "project_root",
            Path(self.project_root).resolve()
        )
        _check_name(self.experiment_name, "MLFLOW_EXPERIMENT_NAME")
        _check_name(self.model_name, "MLFLOW_MODEL_NAME")
        if not _SEMVER.match(self.model_version):
            raise MlopsConfigurationError("MLFLOW_MODEL_VERSION must look like MAJOR.MINOR.PATCH.")
        if not _SHA256.match(self.model_sha256):
            raise MlopsConfigurationError("TRICHURN_MODEL_SHA256 must be a 64-character lowercase hex SHA-256.")
        if self.tracking_uri is not None and not self.tracking_uri.strip():
            raise MlopsConfigurationError("MLFLOW_TRACKING_URI must not be empty.")

    # ---------------------------------------------------------------- derived values
    def resolve(self, path: str | Path) -> Path:
        """Absolute paths are kept; relative ones are anchored at the project root (never at the CWD)."""
        p = Path(path)
        return p if p.is_absolute() else self.project_root / p

    @property
    def model_file(self) -> Path:
        return self.resolve(self.model_path)

    @property
    def metadata_file(self) -> Path:
        return self.model_file.with_suffix(".metadata.json")

    @property
    def local_store(self) -> Path:
        return self.project_root / LOCAL_STORE_DIR

    @property
    def effective_tracking_uri(self) -> str:
        if self.tracking_uri:
            return self.tracking_uri
        return f"sqlite:///{(self.local_store / 'mlflow.db').as_posix()}"

    @property
    def effective_artifact_location(self) -> str:
        if self.artifact_location:
            return self.artifact_location
        return (self.local_store / "artifacts").resolve().as_uri()

    @classmethod
    def from_env(cls, env: Mapping[str, str] | None = None, *, project_root: Path | None = None) -> MlopsSettings:
        e = os.environ if env is None else env
        kwargs: dict[str, object] = {}
        if project_root is not None:
            kwargs["project_root"] = project_root
        if e.get("MLFLOW_TRACKING_URI"):
            kwargs["tracking_uri"] = e["MLFLOW_TRACKING_URI"].strip()
            kwargs["tracking_configured"] = True
        for attr, var in (("artifact_location", "MLFLOW_ARTIFACT_LOCATION"),
                          ("experiment_name", "MLFLOW_EXPERIMENT_NAME"),
                          ("model_name", "MLFLOW_MODEL_NAME"), ("model_version", "MLFLOW_MODEL_VERSION"),
                          ("model_path", "TRICHURN_MODEL_PATH")):
            if e.get(var):
                kwargs[attr] = e[var].strip()
        if e.get("TRICHURN_MODEL_SHA256"):
            kwargs["model_sha256"] = e["TRICHURN_MODEL_SHA256"].strip().lower()
        return cls(**kwargs)  # type: ignore[arg-type]
