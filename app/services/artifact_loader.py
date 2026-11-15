"""Generic, read-only artifact verification and load-once cache (no ML imports).

* Relative paths are resolved by ``Settings.resolve`` (project root), never against the CWD.
* ``verify`` hashes the file (SHA-256, streamed; cached per mtime+size) and compares with an optional pinned digest.
* ``load_once`` verifies, then calls the supplied loader exactly once per process and caches the result.
* Nothing here writes, copies, renames or deletes files. Errors carry the artifact NAME and a reason code only:
  never the path.
"""
from __future__ import annotations

import hashlib
import threading
from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path
from typing import Literal, TypeVar

T = TypeVar("T")
Reason = Literal["missing", "unreadable", "sha256_mismatch"]


class ArtifactUnavailableError(Exception):
    """An artifact is missing, unreadable or failed SHA-256 verification. ``str(exc)`` contains no path."""

    def __init__(self, name: str, reason: Reason):
        super().__init__(f"artifact '{name}': {reason}")
        self.name, self.reason = name, reason


@dataclass(frozen=True)
class ArtifactSpec:
    name: str
    path: Path
    expected_sha256: str | None = None      # None: presence is verified and the digest reported, not pinned


@dataclass(frozen=True)
class ArtifactStatus:
    name: str
    present: bool
    sha256: str | None
    verified: bool                           # present AND (no pin OR digest equals the pin)
    reason: Reason | None = None


def sha256_file(path: Path, chunk_size: int = 1 << 20) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for block in iter(lambda: handle.read(chunk_size), b""):
            digest.update(block)
    return digest.hexdigest()


class ArtifactLoader:
    def __init__(self) -> None:
        self._lock = threading.RLock()
        self._digests: dict[Path, tuple[int, int, str]] = {}      # path -> (mtime_ns, size, sha256)
        self._loaded: dict[tuple[str, Path], object] = {}

    def _digest(self, path: Path) -> str:
        stat = path.stat()
        key = (stat.st_mtime_ns, stat.st_size)
        with self._lock:
            cached = self._digests.get(path)
            if cached and cached[:2] == key:
                return cached[2]
        digest = sha256_file(path)
        with self._lock:
            self._digests[path] = (*key, digest)
        return digest

    def verify(self, spec: ArtifactSpec) -> ArtifactStatus:
        """Never raises: returns the status (including why verification failed)."""
        try:
            if not spec.path.is_file():
                return ArtifactStatus(spec.name, False, None, False, "missing")
            actual = self._digest(spec.path)
        except OSError:
            return ArtifactStatus(spec.name, spec.path.exists(), None, False, "unreadable")
        if spec.expected_sha256 is not None and actual != spec.expected_sha256.lower():
            return ArtifactStatus(spec.name, True, actual, False, "sha256_mismatch")
        return ArtifactStatus(spec.name, True, actual, True)

    def require_verified(self, spec: ArtifactSpec) -> ArtifactStatus:
        status = self.verify(spec)
        if not status.verified:
            raise ArtifactUnavailableError(spec.name, status.reason or "unreadable")
        return status

    def load_once(self, spec: ArtifactSpec, loader: Callable[[Path], T]) -> T:
        """Verify, then call ``loader(path)`` at most once per process for this artifact (thread-safe)."""
        key = (spec.name, spec.path)
        with self._lock:
            if key in self._loaded:
                return self._loaded[key]  # type: ignore[return-value]
            self.require_verified(spec)
            obj = loader(spec.path)
            self._loaded[key] = obj
            return obj
