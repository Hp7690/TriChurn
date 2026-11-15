"""Response schema for the read-only Phase 8 model lifecycle endpoint (leaf module: pydantic only)."""
from __future__ import annotations

from typing import Literal

from pydantic import BaseModel


class IntegrityInfo(BaseModel):
    ok: bool
    reason: str | None = None
    artifact: str
    expected_sha256: str
    actual_sha256: str | None = None
    expected_version: str | None = None
    actual_version: str | None = None


class RegistryInfo(BaseModel):
    status: str
    model_name: str
    registry_version: str | None = None
    semantic_version: str | None = None
    alias: str | None = None
    artifact_sha256: str | None = None
    matches_pinned_sha256: bool | None = None
    error_type: str | None = None


class ModelLifecycleResponse(BaseModel):
    status: Literal["verified", "integrity_failed", "model_missing", "misconfigured"]
    model_version: str | None = None
    integrity: IntegrityInfo | None = None
    registry: RegistryInfo | None = None
