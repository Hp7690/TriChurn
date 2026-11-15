"""Phase 11 service: HTTP schemas <-> the framework-free ``autonomy`` package, plus error translation.

No business arithmetic here (architecture tests forbid it). The Phase 9 retention facade is reused read-only.
"""
from __future__ import annotations

import logging
import threading
from collections.abc import Callable, Mapping
from dataclasses import asdict
from typing import Any, TypeVar

from app.core.autonomy_errors import conflict, feature_disabled, forbidden
from app.core.autonomy_settings import AutonomySettings
from app.core.config import Settings
from app.core.errors import ApiError, ErrorCode, capability_unavailable, internal_error, invalid_input
from app.schemas import autonomy as s
from app.services.retention_service import RetentionService
from autonomy.auth import Authorizer, DenyAllAuthorizer, Reviewer
from autonomy.config import load_autonomy_config
from autonomy.errors import (
    AutonomyConflictError,
    AutonomyError,
    AutonomyForbiddenError,
    AutonomyInputError,
    AutonomyNotFoundError,
    FeatureDisabledError,
)
from autonomy.facade import AutonomyFacade
from autonomy.models import Page
from autonomy.source import Phase9Source
from autonomy.store import AutonomyStore
from retention.errors import PortfolioUnavailableError, RetentionError

logger = logging.getLogger("trichurn.api.autonomy")
T = TypeVar("T")


def _page(page: Page, model: type[Any], extra: dict[str, Any] | None = None) -> dict[str, Any]:
    return {"items": [model.model_validate(asdict(i)) for i in page.items], "total": page.total, "page": page.page,
            "page_size": page.page_size, "page_count": page.page_count, **(extra or {})}


class AutonomyService:
    """The facade is built lazily so a missing artifact or bad configuration never stops the API from starting and
    never affects Phase 6 or Phase 9 endpoints."""

    def __init__(self, settings: Settings, retention: RetentionService,
                 autonomy_settings: AutonomySettings | None = None, authorizer: Authorizer | None = None,
                 facade: AutonomyFacade | None = None):
        self._settings, self._retention = settings, retention
        self._as = autonomy_settings or AutonomySettings()
        self._authorizer = authorizer or DenyAllAuthorizer()
        self._facade_obj = facade
        self._lock = threading.Lock()

    def _facade(self) -> AutonomyFacade:
        with self._lock:
            if self._facade_obj is None:
                try:
                    config = load_autonomy_config(self._as.resolve_config(self._settings))
                except AutonomyInputError as exc:
                    logger.error("Autonomy configuration invalid: %s", exc)
                    raise capability_unavailable("autonomy_configuration") from exc
                source = Phase9Source(self._retention._facade())  # noqa: SLF001 - read-only reuse of Phase 9
                store = AutonomyStore(self._as.resolve_database(self._settings))
                self._facade_obj = AutonomyFacade(source, store, config, self._authorizer)
            return self._facade_obj

    def authenticate(self, headers: Mapping[str, str]) -> Reviewer | None:
        return self._authorizer.authenticate(headers)

    def _run(self, fn: Callable[[AutonomyFacade], T]) -> T:
        try:
            return fn(self._facade())
        except ApiError:
            raise
        except AutonomyInputError as exc:
            raise invalid_input(str(exc)) from exc
        except AutonomyNotFoundError as exc:
            raise ApiError(ErrorCode.NOT_FOUND, str(exc), 404) from exc
        except AutonomyConflictError as exc:
            raise conflict(str(exc)) from exc
        except AutonomyForbiddenError as exc:
            raise forbidden(str(exc)) from exc
        except FeatureDisabledError as exc:
            raise feature_disabled(str(exc)) from exc
        except PortfolioUnavailableError as exc:
            logger.warning("Autonomy portfolio unavailable (%s)", exc.reason)
            raise capability_unavailable("autonomy_portfolio") from exc
        except (AutonomyError, RetentionError) as exc:
            raise internal_error(exc) from exc
        except Exception as exc:  # noqa: BLE001
            raise internal_error(exc) from exc

    # ---------------------------------------------------------------------------------------------- reads
    def summary(self) -> s.SummaryResponse:
        return self._run(lambda f: s.SummaryResponse.model_validate(f.summary()))

    def risks(self, risk_level: str | None, status: str | None, page: int, page_size: int | None) -> s.RiskEventPage:
        return self._run(lambda f: s.RiskEventPage.model_validate(
            _page(f.list_risks(risk_level, status, page, page_size), s.RiskEventOut)))

    def scan(self) -> s.ScanResponse:
        return self._run(lambda f: s.ScanResponse.model_validate(asdict(f.scan_risks())))

    def recommendations(self, status: str | None, category: str | None, priority: str | None, risk_band: str | None,
                        customer_id: str | None, page: int, page_size: int | None) -> s.RecommendationPage:
        return self._run(lambda f: s.RecommendationPage.model_validate(_page(
            f.list_recommendations(status, category, priority, risk_band, customer_id, page, page_size),
            s.RecommendationOut)))

    def recommendation(self, recommendation_id: str) -> s.RecommendationDetail:
        return self._run(lambda f: s.RecommendationDetail.model_validate(
            asdict(f.get_recommendation(recommendation_id))))

    def generate(self, request: s.GenerateRequest) -> s.GenerateResponse:
        return self._run(lambda f: s.GenerateResponse.model_validate(
            asdict(f.generate_recommendations(request.customer_ids or None, request.limit))))

    def feedback(self, page: int, page_size: int | None) -> s.FeedbackPage:
        return self._run(lambda f: s.FeedbackPage.model_validate(
            _page(f.list_feedback(page, page_size), s.FeedbackOut)))

    def learning(self) -> s.LearningResponse:
        return self._run(lambda f: s.LearningResponse.model_validate(f.learning_report()))

    def audit(self, event_type: str | None, recommendation_id: str | None, customer_id: str | None, page: int,
              page_size: int | None) -> s.AuditPage:
        return self._run(lambda f: s.AuditPage.model_validate(_page(
            f.list_audit(event_type, recommendation_id, customer_id, page, page_size), s.AuditEventOut)))

    # ------------------------------------------------------------------------------------------- workflow
    def transition(self, recommendation_id: str, action: str, reviewer: Reviewer | None, request: s.TransitionRequest,
                   idempotency_key: str | None) -> s.TransitionResponse:
        return self._run(lambda f: s.TransitionResponse.model_validate(
            asdict(f.transition(recommendation_id, action, reviewer, request.note, idempotency_key))))

    def record_feedback(self, reviewer: Reviewer | None, request: s.FeedbackRequest,
                        idempotency_key: str | None) -> s.FeedbackResponse:
        return self._run(lambda f: s.FeedbackResponse.model_validate(asdict(f.record_feedback(
            reviewer, request.recommendation_id, request.outcome, request.outcome_at, request.campaign_id,
            request.data_source, idempotency_key))))


def build_autonomy_service(settings: Settings, retention: RetentionService) -> AutonomyService:
    """Composition helper used by ``create_app``. No I/O: everything is created lazily on first request."""
    import os

    return AutonomyService(settings, retention, AutonomySettings.from_env(os.environ))
