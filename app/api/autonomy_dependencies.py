from __future__ import annotations

from fastapi import Request

from app.services.autonomy_service import AutonomyService
from autonomy.auth import Reviewer


def get_autonomy(request: Request) -> AutonomyService:
    return request.app.state.autonomy


def get_reviewer(request: Request) -> Reviewer | None:
    """The authenticated reviewer, or None. Today no identity provider exists, so this is always None."""
    return request.app.state.autonomy.authenticate(request.headers)
