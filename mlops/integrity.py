"""Reusable, read-only integrity verification for a model artifact (stdlib only: no mlflow, no ML imports).

Order of trust: bytes -> SHA-256 -> compare with the PINNED digest -> (optionally) cross-check the sidecar metadata.
Nothing is deserialised here; ``mlops.loading`` calls this BEFORE any joblib/pickle load.
"""
from __future__ import annotations

import hashlib
import json
import re
from dataclasses import dataclass
from pathlib import Path

from mlops.errors import ModelIntegrityError

_SHA256 = re.compile(r"^[0-9a-f]{64}$")


@dataclass(frozen=True)
class IntegrityReport:
    ok: bool
    reason: str | None                 # None when ok
    artifact: str                      # file NAME only, never a path
    expected_sha256: str
    actual_sha256: str | None
    expected_version: str | None = None
    actual_version: str | None = None

    def to_dict(self) -> dict[str, object]:
        return {"ok": self.ok, "reason": self.reason, "artifact": self.artifact,
                "expected_sha256": self.expected_sha256, "actual_sha256": self.actual_sha256,
                "expected_version": self.expected_version, "actual_version": self.actual_version}


def sha256_file(path: Path, chunk_size: int = 1 << 20) -> str:
    digest = hashlib.sha256()
    with Path(path).open("rb") as handle:
        for block in iter(lambda: handle.read(chunk_size), b""):
            digest.update(block)
    return digest.hexdigest()


def verify_model_artifact(path: str | Path, expected_sha256: str, *, metadata_path: str | Path | None = None,
                          expected_version: str | None = None) -> IntegrityReport:
    """Return a report; never raises for an expected failure (missing/unreadable/mismatch)."""
    p = Path(path)
    expected = (expected_sha256 or "").strip().lower()
    base = {"artifact": p.name, "expected_sha256": expected, "expected_version": expected_version}
    if not _SHA256.match(expected):
        return IntegrityReport(False, "invalid_expected_sha256", actual_sha256=None, **base)
    if not p.is_file():
        return IntegrityReport(False, "missing", actual_sha256=None, **base)
    try:
        actual = sha256_file(p)
    except OSError:
        return IntegrityReport(False, "unreadable", actual_sha256=None, **base)
    if actual != expected:
        return IntegrityReport(False, "sha256_mismatch", actual_sha256=actual, **base)
    actual_version = None
    if metadata_path is not None:
        try:
            sidecar = json.loads(Path(metadata_path).read_text(encoding="utf-8"))
            if not isinstance(sidecar, dict):
                raise ValueError("not an object")
        except (OSError, ValueError):
            return IntegrityReport(False, "metadata_unreadable", actual_sha256=actual, **base)
        actual_version = sidecar.get("model_version")
        recorded = str(sidecar.get("artifact_sha256", "")).lower()
        if recorded != actual:
            return IntegrityReport(False, "metadata_sha256_mismatch", actual_sha256=actual,
                                   actual_version=actual_version, **base)
        if expected_version is not None and actual_version != expected_version:
            return IntegrityReport(False, "version_mismatch", actual_sha256=actual,
                                   actual_version=actual_version, **base)
    return IntegrityReport(True, None, actual_sha256=actual, actual_version=actual_version, **base)


def require_verified(path: str | Path, expected_sha256: str, *, metadata_path: str | Path | None = None,
                     expected_version: str | None = None) -> IntegrityReport:
    """Like ``verify_model_artifact`` but raises ``ModelIntegrityError`` (name + reason only) on any failure."""
    report = verify_model_artifact(path, expected_sha256, metadata_path=metadata_path,
                                   expected_version=expected_version)
    if not report.ok:
        raise ModelIntegrityError(report.artifact, report.reason or "unknown")
    return report
