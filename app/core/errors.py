"""Uniform, sanitised error responses.

Every error the API returns has the shape ``{"error": {"code", "message", "details"?, "error_id"?}}``. Responses never
contain stack traces, file-system paths, environment variables or the text of internal Python exceptions: unexpected
errors are logged server-side under a short ``error_id`` and the client only receives that id.
"""
from __future__ import annotations

import logging
import uuid
from enum import StrEnum
from typing import Any

from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from starlette.exceptions import HTTPException as StarletteHTTPException

logger = logging.getLogger("trichurn.api")


class ErrorCode(StrEnum):
    INVALID_INPUT = "INVALID_INPUT"
    NOT_FOUND = "NOT_FOUND"
    METHOD_NOT_ALLOWED = "METHOD_NOT_ALLOWED"
    INTEGRATION_NOT_CONFIGURED = "INTEGRATION_NOT_CONFIGURED"
    ARTIFACT_UNAVAILABLE = "ARTIFACT_UNAVAILABLE"
    CAPABILITY_UNAVAILABLE = "CAPABILITY_UNAVAILABLE"
    INCONSISTENT_RESULTS = "INCONSISTENT_RESULTS"
    INTERNAL_ERROR = "INTERNAL_ERROR"


class ApiError(Exception):
    """An error that is safe to show to the client (code + fixed message + optional field details)."""

    def __init__(self, code: ErrorCode, message: str, status_code: int,
                 details: list[dict[str, str]] | None = None, error_id: str | None = None):
        super().__init__(message)
        self.code, self.message, self.status_code = code, message, status_code
        self.details, self.error_id = details, error_id


def invalid_input(message: str = "Invalid customer features.",
                  details: list[dict[str, str]] | None = None) -> ApiError:
    return ApiError(ErrorCode.INVALID_INPUT, message, 422, details)


def capability_unavailable(capability: str) -> ApiError:
    return ApiError(ErrorCode.CAPABILITY_UNAVAILABLE, f"The '{capability}' capability is currently unavailable.", 503)


def artifact_unavailable(name: str) -> ApiError:
    return ApiError(ErrorCode.ARTIFACT_UNAVAILABLE,
                    f"The '{name}' artifact is unavailable or failed verification.", 503)


def integration_not_configured() -> ApiError:
    return ApiError(ErrorCode.INTEGRATION_NOT_CONFIGURED,
                    "The Phase 1-5 integration is not configured or could not be loaded.", 503)


def inconsistent_results() -> ApiError:
    return ApiError(ErrorCode.INCONSISTENT_RESULTS,
                    "Internal consistency check failed; the result was withheld.", 500)


def internal_error(exc: BaseException | None = None) -> ApiError:
    """Log the real exception server-side; hand the client only an opaque id."""
    error_id = uuid.uuid4().hex[:12]
    logger.error("Unexpected error [%s]", error_id, exc_info=exc)
    return ApiError(ErrorCode.INTERNAL_ERROR, "An internal error occurred.", 500, error_id=error_id)


def _body(code: str, message: str, details: list[dict[str, str]] | None = None,
          error_id: str | None = None) -> dict[str, Any]:
    error: dict[str, Any] = {"code": code, "message": message}
    if details:
        error["details"] = details
    if error_id:
        error["error_id"] = error_id
    return {"error": error}


def sanitize_validation_errors(errors: list[dict[str, Any]]) -> list[dict[str, str]]:
    """Field path + pydantic message only. The submitted value (``input``) and ``ctx`` are deliberately dropped."""
    out = []
    for err in errors:
        loc = [str(part) for part in err.get("loc", ()) if part != "body"]
        out.append({"field": ".".join(loc) or "body", "message": str(err.get("msg", "Invalid value."))})
    return out


def install_error_handlers(app: FastAPI) -> None:
    @app.exception_handler(ApiError)
    async def _api_error(_: Request, exc: ApiError) -> JSONResponse:
        return JSONResponse(_body(exc.code, exc.message, exc.details, exc.error_id), status_code=exc.status_code)

    @app.exception_handler(RequestValidationError)
    async def _validation(_: Request, exc: RequestValidationError) -> JSONResponse:
        details = sanitize_validation_errors(list(exc.errors()))
        about_features = any(d["field"].startswith("features") for d in details)
        message = "Invalid customer features." if about_features else "Invalid request."
        return JSONResponse(_body(ErrorCode.INVALID_INPUT, message, details), status_code=422)

    @app.exception_handler(StarletteHTTPException)
    async def _http(_: Request, exc: StarletteHTTPException) -> JSONResponse:
        if exc.status_code == 404:
            return JSONResponse(_body(ErrorCode.NOT_FOUND, "Resource not found."), status_code=404)
        if exc.status_code == 405:
            return JSONResponse(_body(ErrorCode.METHOD_NOT_ALLOWED, "Method not allowed."), status_code=405,
                                headers=dict(exc.headers or {}))
        return JSONResponse(_body(ErrorCode.INVALID_INPUT, "The request could not be processed."),
                            status_code=exc.status_code)

    @app.exception_handler(Exception)
    async def _unexpected(_: Request, exc: Exception) -> JSONResponse:       # last resort
        err = internal_error(exc)
        return JSONResponse(_body(err.code, err.message, error_id=err.error_id), status_code=500)
