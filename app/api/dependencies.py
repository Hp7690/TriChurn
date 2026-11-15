from __future__ import annotations

from fastapi import Request

from app.core.config import Settings
from app.services.container import Services


def get_services(request: Request) -> Services:
    return request.app.state.services


def get_settings(request: Request) -> Settings:
    return request.app.state.settings
