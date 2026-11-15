"""Phase 12 - Customer Value & Revenue Intelligence endpoints (all under /api/v1/revenue-intelligence).

Read-only analytics. Nothing here contacts customers, executes offers, changes billing data or trains a model.
Errors use the TriChurn envelope: {"error": {"code": ..., "message": ...}}.
"""
from __future__ import annotations

import threading
from collections.abc import Callable
from typing import Annotated, Any, Literal

from fastapi import APIRouter, Depends, Query, Request, Response
from fastapi.responses import JSONResponse
from fastapi.routing import APIRoute

from app.schemas import revenue_intelligence as s
from app.services.revenue_intelligence_service import (
    RevenueIntelligenceService,
    ServiceError,
    build_revenue_service,
)

_LOCK = threading.Lock()


class RevenueRoute(APIRoute):
    """Translate domain errors to the TriChurn error envelope for this router only."""

    def get_route_handler(self) -> Callable:
        original = super().get_route_handler()

        async def handler(request: Request) -> Response:
            try:
                return await original(request)
            except ServiceError as exc:
                return JSONResponse({"error": {"code": exc.code, "message": exc.message}}, status_code=exc.status)
        return handler


router = APIRouter(prefix="/revenue-intelligence", tags=["revenue-intelligence"], route_class=RevenueRoute)
ERR = {422: {"description": "Invalid input"}, 503: {"description": "Data or configuration unavailable"},
       500: {"description": "Internal error"}}


def get_service(request: Request) -> RevenueIntelligenceService:
    svc = getattr(request.app.state, "revenue_intelligence", None)
    if svc is None:
        with _LOCK:
            svc = getattr(request.app.state, "revenue_intelligence", None)
            if svc is None:
                svc = build_revenue_service()
                request.app.state.revenue_intelligence = svc
    return svc


Svc = Annotated[RevenueIntelligenceService, Depends(get_service)]
PageQ = Annotated[int, Query(ge=1, le=100000)]
SizeQ = Annotated[int | None, Query(ge=1, le=200)]
SegQ = Annotated[str | None, Query(max_length=30)]
IdQ = Annotated[str | None, Query(max_length=64, pattern=r"^[A-Za-z0-9_.\-]+$")]


def _run(svc: RevenueIntelligenceService, name: str, *a: Any, **k: Any) -> Any:
    return svc.call(name, *a, **k)


@router.get("/summary", response_model=s.SummaryResponse, responses=ERR, summary="Executive summary")
def summary(svc: Svc):
    return _run(svc, "summary")


@router.get("/clv/summary", response_model=s.ClvSummaryResponse, responses=ERR, summary="CLV summary")
def clv_summary(svc: Svc):
    return _run(svc, "clv_summary")


@router.get("/clv/customers", response_model=s.ClvCustomersResponse, responses=ERR, summary="Customer CLV (paged)")
def clv_customers(svc: Svc, page: PageQ = 1, page_size: SizeQ = None, segment: SegQ = None,
                  customer_id: IdQ = None,
                  sort_by: Literal["customer_id", "observed_billing", "estimated_clv", "monthly_charges",
                                   "tenure"] = "customer_id", descending: bool = False):
    return _run(svc, "clv_customers", page, page_size, segment, sort_by, descending, customer_id)


@router.get("/clv/segments", response_model=s.ClvSegmentsResponse, responses=ERR, summary="Value segments")
def clv_segments(svc: Svc):
    return _run(svc, "clv_segments")


@router.get("/revenue-at-risk/summary", response_model=s.RiskSummaryResponse, responses=ERR,
            summary="Revenue exposure summary")
def risk_summary(svc: Svc):
    return _run(svc, "risk_summary")


@router.get("/revenue-at-risk/customers", response_model=s.RiskCustomersResponse, responses=ERR,
            summary="Rule-flagged customers (paged)")
def risk_customers(svc: Svc, page: PageQ = 1, page_size: SizeQ = None,
                   contract: Annotated[str | None, Query(max_length=40)] = None, segment: SegQ = None,
                   tenure_group: Annotated[str | None, Query(max_length=20)] = None):
    return _run(svc, "risk_customers", page, page_size, contract, segment, tenure_group)


@router.get("/opportunities/summary", response_model=s.OpportunitiesSummaryResponse, responses=ERR,
            summary="Upsell / cross-sell summary (advisory)")
def opp_summary(svc: Svc):
    return _run(svc, "opportunities_summary")


@router.get("/opportunities/customers", response_model=s.OpportunitiesCustomersResponse, responses=ERR,
            summary="Advisory opportunities (paged)")
def opp_customers(svc: Svc, page: PageQ = 1, page_size: SizeQ = None,
                  recommendation_type: Annotated[str | None, Query(max_length=40)] = None,
                  eligibility: Annotated[str | None, Query(max_length=40)] = None, segment: SegQ = None,
                  customer_id: IdQ = None):
    return _run(svc, "opportunities_customers", page, page_size, recommendation_type, eligibility, segment,
                customer_id)


@router.get("/cohorts/summary", response_model=s.CohortSummaryResponse, responses=ERR, summary="Cohort summary")
def cohort_summary(svc: Svc):
    return _run(svc, "cohort_summary")


@router.get("/cohorts/tenure", response_model=s.CohortTenureResponse, responses=ERR,
            summary="Tenure-based cohorts (TENURE_BASED_PROXY)")
def cohort_tenure(svc: Svc):
    return _run(svc, "cohort_tenure")


@router.get("/forecast/readiness", response_model=s.ForecastReadinessResponse, response_model_by_alias=True,
            responses=ERR, summary="Forecast readiness")
def forecast_readiness(svc: Svc):
    return _run(svc, "forecast_readiness")


@router.post("/forecast/validate", response_model=s.ForecastReadinessResponse, response_model_by_alias=True,
             responses=ERR, summary="Validate supplied revenue history (no forecast is produced)")
def forecast_validate(body: s.ForecastValidateRequest, svc: Svc):
    rows = [r.model_dump(exclude_none=True) for r in body.rows]
    return _run(svc, "forecast_validate", rows, body.run_backtest)


@router.get("/availability", response_model=s.AvailabilityResponse, responses=ERR,
            summary="Data availability and metric definitions")
def availability(svc: Svc):
    return _run(svc, "availability")
