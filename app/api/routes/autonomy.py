"""Phase 11 - Autonomous Retention Intelligence endpoints (all under /api/v1/autonomous-retention).

Read endpoints and non-consequential generation/scan work for everyone. Approve / reject / cancel / execute and
feedback need an authenticated reviewer; with no identity provider configured they return 403 by design.
Nothing here contacts customers or any external system.
"""
from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Depends, Header, Path, Query

from app.api.autonomy_dependencies import get_autonomy, get_reviewer
from app.schemas import autonomy as s
from app.schemas.common import ErrorResponse
from app.services.autonomy_service import AutonomyService
from autonomy.auth import Reviewer

router = APIRouter(prefix="/autonomous-retention", tags=["autonomous-retention"])
ERRORS = {403: {"model": ErrorResponse}, 404: {"model": ErrorResponse}, 409: {"model": ErrorResponse},
          422: {"model": ErrorResponse}, 500: {"model": ErrorResponse}, 503: {"model": ErrorResponse}}
Service = Annotated[AutonomyService, Depends(get_autonomy)]
Reviewer_ = Annotated[Reviewer | None, Depends(get_reviewer)]
PageQ = Annotated[int, Query(ge=1, le=100000)]
SizeQ = Annotated[int | None, Query(ge=1, le=100)]
IdemKey = Annotated[str | None, Header(alias="Idempotency-Key", max_length=100)]
RecPath = Annotated[str, Path(min_length=1, max_length=40, pattern=r"^[A-Za-z0-9_\-]+$")]


@router.get("/summary", response_model=s.SummaryResponse, responses=ERRORS, summary="Command-center summary")
def summary(service: Service) -> s.SummaryResponse:
    return service.summary()


@router.get("/risks", response_model=s.RiskEventPage, responses=ERRORS,
            summary="Risk-change events from batch snapshot comparison (not real-time)")
def risks(service: Service, page: PageQ = 1, page_size: SizeQ = None,
          risk_level: Annotated[str | None, Query(max_length=20)] = None,
          status: Annotated[str | None, Query(max_length=20)] = None) -> s.RiskEventPage:
    return service.risks(risk_level, status, page, page_size)


@router.post("/risks/scan", response_model=s.ScanResponse, responses=ERRORS,
             summary="Store a snapshot of the scored portfolio and compare it with the previous one")
def scan(service: Service) -> s.ScanResponse:
    return service.scan()


@router.get("/recommendations", response_model=s.RecommendationPage, responses=ERRORS,
            summary="List recommendations")
def recommendations(service: Service, page: PageQ = 1, page_size: SizeQ = None,
                    status: Annotated[str | None, Query(max_length=20)] = None,
                    category: Annotated[str | None, Query(max_length=60)] = None,
                    priority: Annotated[str | None, Query(max_length=10)] = None,
                    risk_band: Annotated[str | None, Query(max_length=20)] = None,
                    customer_id: Annotated[str | None, Query(max_length=64, pattern=r"^[A-Za-z0-9_.\-]+$")] = None,
                    ) -> s.RecommendationPage:
    return service.recommendations(status, category, priority, risk_band, customer_id, page, page_size)


@router.post("/recommendations/generate", response_model=s.GenerateResponse, responses=ERRORS,
             summary="Generate rule-based recommendations (idempotent; sends nothing)")
def generate(request: s.GenerateRequest, service: Service) -> s.GenerateResponse:
    return service.generate(request)


@router.get("/recommendations/{recommendation_id}", response_model=s.RecommendationDetail, responses=ERRORS,
            summary="One recommendation with its audit history")
def recommendation(recommendation_id: RecPath, service: Service) -> s.RecommendationDetail:
    return service.recommendation(recommendation_id)


@router.get("/approvals", response_model=s.RecommendationPage, responses=ERRORS,
            summary="Recommendations in the approval workflow (defaults to pending)")
def approvals(service: Service, page: PageQ = 1, page_size: SizeQ = None,
              status: Annotated[str | None, Query(max_length=20)] = "pending") -> s.RecommendationPage:
    return service.recommendations(status, None, None, None, None, page, page_size)


@router.post("/approvals/{recommendation_id}/{action}", response_model=s.TransitionResponse, responses=ERRORS,
             summary="approve | reject | cancel | execute | fail (needs an authenticated reviewer and Idempotency-Key)")
def transition(recommendation_id: RecPath, action: s.Action, request: s.TransitionRequest, service: Service,
               reviewer: Reviewer_, idempotency_key: IdemKey = None) -> s.TransitionResponse:
    return service.transition(recommendation_id, action, reviewer, request, idempotency_key)


@router.get("/feedback", response_model=s.FeedbackPage, responses=ERRORS, summary="Observed outcome records")
def feedback(service: Service, page: PageQ = 1, page_size: SizeQ = None) -> s.FeedbackPage:
    return service.feedback(page, page_size)


@router.post("/feedback", response_model=s.FeedbackResponse, responses=ERRORS,
             summary="Record an OBSERVED outcome (executed recommendations only; needs a reviewer and Idempotency-Key)")
def record_feedback(request: s.FeedbackRequest, service: Service, reviewer: Reviewer_,
                    idempotency_key: IdemKey = None) -> s.FeedbackResponse:
    return service.record_feedback(reviewer, request, idempotency_key)


@router.get("/learning", response_model=s.LearningResponse, responses=ERRORS,
            summary="Feedback evaluation and learning readiness (learning is not enabled)")
def learning(service: Service) -> s.LearningResponse:
    return service.learning()


@router.get("/audit", response_model=s.AuditPage, responses=ERRORS, summary="Append-only audit trail")
def audit(service: Service, page: PageQ = 1, page_size: SizeQ = None,
          event_type: Annotated[str | None, Query(max_length=40)] = None,
          recommendation_id: Annotated[str | None, Query(max_length=40)] = None,
          customer_id: Annotated[str | None, Query(max_length=64, pattern=r"^[A-Za-z0-9_.\-]+$")] = None
          ) -> s.AuditPage:
    return service.audit(event_type, recommendation_id, customer_id, page, page_size)
