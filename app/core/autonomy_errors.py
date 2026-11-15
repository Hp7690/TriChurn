"""Error codes added by Phase 11 (the locked ``ErrorCode`` enum is left untouched)."""
from __future__ import annotations

from enum import StrEnum

from app.core.errors import ApiError


class AutonomyErrorCode(StrEnum):
    FORBIDDEN = "FORBIDDEN"
    FEATURE_DISABLED = "FEATURE_DISABLED"
    CONFLICT = "CONFLICT"


def forbidden(message: str) -> ApiError:
    return ApiError(AutonomyErrorCode.FORBIDDEN, message, 403)  # type: ignore[arg-type]


def feature_disabled(message: str) -> ApiError:
    return ApiError(AutonomyErrorCode.FEATURE_DISABLED, message, 403)  # type: ignore[arg-type]


def conflict(message: str) -> ApiError:
    return ApiError(AutonomyErrorCode.CONFLICT, message, 409)  # type: ignore[arg-type]
