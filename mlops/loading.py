"""Model loading: verify the digest FIRST, deserialise only afterwards, through the existing Phase 3 loader.

    registry (optional) -> artifact on disk -> integrity verification -> ml.explainability.load_verified_artifact

The prediction algorithm is untouched: this module only decides WHETHER the locked artifact may be loaded.
"""
from __future__ import annotations

from typing import Any

from mlops.config import MlopsSettings
from mlops.errors import ModelIntegrityError
from mlops.integrity import require_verified


def load_verified_model(settings: MlopsSettings) -> Any:
    """Return the existing ``VerifiedArtifact`` (``.artifact.predict_proba``, ``.threshold``, ``.metadata``).

    Raises ``ModelIntegrityError`` (name + reason, no path) if the file is missing/unreadable/altered, BEFORE any
    unpickling happens. Never touches MLflow: it works offline."""
    require_verified(settings.model_file, settings.model_sha256, metadata_path=settings.metadata_file,
                     expected_version=settings.model_version)
    from ml.errors import ArtifactIntegrityError  # noqa: PLC0415  (Phase 1-5 package, imported lazily)
    from ml.explainability import load_verified_artifact  # noqa: PLC0415
    try:
        return load_verified_artifact(settings.model_file, settings.metadata_file,
                                      expected_sha256=settings.model_sha256)
    except ArtifactIntegrityError as exc:
        raise ModelIntegrityError(settings.model_file.name, "load_failed") from exc
