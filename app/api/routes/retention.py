"""Phase 9 - Advanced Retention Intelligence endpoints (all under /api/v1/retention).

Figures are ESTIMATES under assumed action costs and success rates (Phase 4 configuration); campaign analytics show
only what users recorded. Nothing here claims causal uplift.
"""
from __future__ import annotations

from typing import Annotated, Literal

from fastapi import APIRouter, Depends, Path, Query

from app.api.retention_dependencies import get_retention
from app.schemas import retention as s
from app.schemas.common import ErrorResponse
from app.services.retention_service import RetentionService

router = APIRouter(prefix="/retention", tags=["retention"])
ERRORS = {404: {"model": ErrorResponse}, 422: {"model": ErrorResponse},
          500: {"model": ErrorResponse}, 503: {"model": ErrorResponse}}
Service = Annotated[RetentionService, Depends(get_retention)]
CustomerPath = Annotated[str, Path(min_length=1, max_length=64, pattern=r"^[A-Za-z0-9_.\-]+$")]
CampaignPath = Annotated[str, Path(min_length=1, max_length=40, pattern=r"^[A-Za-z0-9_\-]+$")]


@router.get("/summary", response_model=s.ExecutiveSummaryResponse, responses=ERRORS,
            summary="Executive retention summary (estimates)")
def summary(service: Service) -> s.ExecutiveSummaryResponse:
    return service.summary()


@router.get("/priorities", response_model=s.PriorityPageResponse, responses=ERRORS,
            summary="Ranked retention priorities (heuristic score), paginated")
def priorities(
    service: Service,
    page: Annotated[int, Query(ge=1, le=100000)] = 1,
    page_size: Annotated[int, Query(ge=1, le=200)] = 25,
    search: Annotated[str | None, Query(max_length=64)] = None,
    risk_band: Annotated[str | None, Query(max_length=20)] = None,
    segment_id: Annotated[int | None, Query(ge=0, le=100)] = None,
    decision: Annotated[Literal["INTERVENE", "DO_NOT_INTERVENE"] | None, Query()] = None,
    tier: Annotated[Literal["P1", "P2", "P3", "P4", "MONITOR"] | None, Query()] = None,
    min_churn_probability: Annotated[float | None, Query(ge=0, le=1)] = None,
    sort_by: Annotated[Literal["rank", "priority_score", "churn_probability", "value_at_risk", "clv",
                               "expected_net_benefit"], Query()] = "rank",
    descending: bool = False,
) -> s.PriorityPageResponse:
    return service.priorities(search, risk_band, segment_id, decision, tier, min_churn_probability, sort_by,
                              descending, page, page_size)


@router.get("/actions", response_model=s.ActionsResponse, responses=ERRORS,
            summary="Phase 4 retention action catalogue (single source of truth)")
def actions(service: Service) -> s.ActionsResponse:
    return service.actions()


@router.get("/customers/{customer_id}/recommendation", response_model=s.RecommendationResponse, responses=ERRORS,
            summary="Campaign recommendation for one customer, with reasons")
def recommendation(customer_id: CustomerPath, service: Service) -> s.RecommendationResponse:
    return service.recommendation(customer_id)


@router.post("/simulate", response_model=s.SimulateResponse, responses=ERRORS,
             summary="Compare retention campaign scenarios (estimates under assumptions)")
def simulate(request: s.SimulateRequest, service: Service) -> s.SimulateResponse:
    return service.simulate(request)


@router.post("/campaigns", response_model=s.CampaignOut, status_code=201, responses=ERRORS,
             summary="Create a campaign record")
def create_campaign(request: s.CampaignCreateRequest, service: Service) -> s.CampaignOut:
    return service.create_campaign(request)


@router.get("/campaigns", response_model=s.CampaignListResponse, responses=ERRORS, summary="List campaigns")
def list_campaigns(service: Service) -> s.CampaignListResponse:
    return service.list_campaigns()


@router.get("/campaigns/{campaign_id}", response_model=s.CampaignMetricsOut, responses=ERRORS,
            summary="Campaign performance (estimated and actual kept separate)")
def campaign(campaign_id: CampaignPath, service: Service) -> s.CampaignMetricsOut:
    return service.campaign(campaign_id)


@router.post("/campaigns/{campaign_id}/assignments", response_model=s.AssignResponse, responses=ERRORS,
             summary="Assign customers to a campaign")
def assign(campaign_id: CampaignPath, request: s.AssignRequest, service: Service) -> s.AssignResponse:
    return service.assign(campaign_id, request)


@router.post("/campaigns/{campaign_id}/outcomes", response_model=s.OutcomeResponse, responses=ERRORS,
             summary="Record observed campaign outcomes (once per assignment)")
def record_outcomes(campaign_id: CampaignPath, request: s.OutcomeRequest, service: Service) -> s.OutcomeResponse:
    return service.record_outcomes(campaign_id, request)


@router.get("/analytics", response_model=s.AnalyticsResponse, responses=ERRORS,
            summary="Campaign analytics from recorded data only")
def analytics(service: Service) -> s.AnalyticsResponse:
    return service.analytics()


@router.get("/uplift-readiness", response_model=s.UpliftReadinessResponse, responses=ERRORS,
            summary="Is there enough treatment/control evidence for uplift modelling? (checks only)")
def uplift_readiness(service: Service) -> s.UpliftReadinessResponse:
    return service.uplift_readiness()
