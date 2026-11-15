from __future__ import annotations

from fastapi import Request

from app.services.retention_service import RetentionService


def get_retention(request: Request) -> RetentionService:
    return request.app.state.retention
