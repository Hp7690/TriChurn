"""TriChurn Phase 8 - productionization: MLflow tracking, Model Registry and artifact integrity.

Deliberately NOT named ``mlflow`` (that would shadow the real library). Importing this package never imports mlflow
or the ML stack; those are loaded lazily by the functions that need them.
"""
from mlops.config import MlopsSettings
from mlops.errors import MlopsConfigurationError, MlopsError, ModelIntegrityError, RegistryError
from mlops.integrity import IntegrityReport, require_verified, sha256_file, verify_model_artifact

__version__ = "8.0.0"
__all__ = ["IntegrityReport", "MlopsConfigurationError", "MlopsError", "MlopsSettings", "ModelIntegrityError",
           "RegistryError", "require_verified", "sha256_file", "verify_model_artifact"]
