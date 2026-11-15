"""Phase 9 service: translates between the HTTP schemas and the framework-free ``retention`` package.

No business arithmetic lives here (the architecture tests forbid it): every figure is computed in ``retention`` from
the locked Phase 2/4/5 results. Domain errors become the project's uniform error envelope.
"""
from __future__ import annotations

import logging
import threading
from collections.abc import Callable
from dataclasses import asdict
from typing import Any, TypeVar

from app.core.config import Settings
from app.core.errors import ApiError, ErrorCode, capability_unavailable, internal_error, invalid_input
from app.core.retention_settings import RetentionSettings
from app.schemas import retention as s
from app.services.adapters.interface import Phase15Port
from retention import ESTIMATE_NOTE, SCORE_NOTE
from retention.campaign_store import CampaignStore, NewOutcome
from retention.config import load_retention_config
from retention.errors import (
    PortfolioUnavailableError,
    RetentionError,
    RetentionInputError,
    RetentionNotFoundError,
)
from retention.facade import RetentionFacade
from retention.prioritization import PriorityEntry, PriorityFilter
from retention.recommendation import Driver
from retention.scoring import ArtifactPortfolioProvider, PortfolioProvider, ScoringSources
from retention.simulator import ScenarioSpec

logger = logging.getLogger("trichurn.api.retention")
T = TypeVar("T")
TOP_DRIVERS = 5


def _snapshot(entry: PriorityEntry) -> dict[str, Any]:
    return asdict(entry.customer)


def _priority_item(entry: PriorityEntry, reasons: tuple[str, ...] = ()) -> s.PriorityItem:
    c = entry.components
    return s.PriorityItem(
        rank=entry.rank, score=entry.score, tier=entry.tier, customer=s.CustomerSnapshot(**{
            k: v for k, v in _snapshot(entry).items() if k in s.CustomerSnapshot.model_fields}),
        value_at_risk_percentile=c.value_at_risk_percentile,
        churn_probability_percentile=c.churn_probability_percentile,
        expected_net_benefit_percentile=c.expected_net_benefit_percentile, reasons=list(reasons))


class RetentionService:
    """The facade is created lazily so a missing artifact or bad config never prevents the API from starting and
    never affects the Phase 6 endpoints."""

    def __init__(self, settings: Settings, retention_settings: RetentionSettings | None = None,
                 adapter: Phase15Port | None = None, provider: PortfolioProvider | None = None,
                 store: CampaignStore | None = None):
        self._settings = settings
        self._rs = retention_settings or RetentionSettings()
        self._adapter = adapter
        self._provider = provider
        self._store = store
        self._facade_obj: RetentionFacade | None = None
        self._lock = threading.Lock()

    # ------------------------------------------------------------------------------------------ plumbing
    def _facade(self) -> RetentionFacade:
        with self._lock:
            if self._facade_obj is None:
                try:
                    config = load_retention_config(self._rs.resolve_config(self._settings))
                except RetentionInputError as exc:
                    logger.error("Retention configuration invalid: %s", exc)
                    raise capability_unavailable("retention_configuration") from exc
                st = self._settings
                provider = self._provider or ArtifactPortfolioProvider(ScoringSources(
                    st.resolve(st.phase2_model_path), st.phase2_expected_sha256, st.resolve(st.phase5_model_path),
                    st.phase5_expected_sha256, st.resolve(st.dataset_csv_path), st.resolve(st.dataset_spec_path)))
                store = self._store or CampaignStore(self._rs.resolve_database(st))
                self._facade_obj = RetentionFacade(provider, store, config)
            return self._facade_obj

    def _run(self, fn: Callable[[RetentionFacade], T]) -> T:
        try:
            return fn(self._facade())
        except ApiError:
            raise
        except RetentionInputError as exc:
            raise invalid_input(str(exc)) from exc
        except RetentionNotFoundError as exc:
            raise ApiError(ErrorCode.NOT_FOUND, str(exc), 404) from exc
        except PortfolioUnavailableError as exc:
            logger.warning("Retention portfolio unavailable (%s)", exc.reason)
            raise capability_unavailable("retention_portfolio") from exc
        except RetentionError as exc:
            raise internal_error(exc) from exc
        except Exception as exc:  # noqa: BLE001
            raise internal_error(exc) from exc

    # --------------------------------------------------------------------------------------------- reads
    def summary(self) -> s.ExecutiveSummaryResponse:
        def build(f: RetentionFacade) -> s.ExecutiveSummaryResponse:
            data = f.summary()
            payload = asdict(data)
            payload["top_priorities"] = [_priority_item(e).model_dump() for e in data.top_priorities]
            return s.ExecutiveSummaryResponse.model_validate(payload)
        return self._run(build)

    def priorities(self, search: str | None, risk_band: str | None, segment_id: int | None, decision: str | None,
                   tier: str | None, min_churn_probability: float | None, sort_by: str, descending: bool,
                   page: int, page_size: int) -> s.PriorityPageResponse:
        def build(f: RetentionFacade) -> s.PriorityPageResponse:
            flt = PriorityFilter(search, risk_band, segment_id, decision, tier, min_churn_probability)
            result, reasons = f.priorities(flt, sort_by, descending, page, page_size)
            return s.PriorityPageResponse(
                items=[_priority_item(e, reasons[e.customer.customer_id]) for e in result.items],
                total=result.total, page=result.page, page_size=result.page_size, page_count=result.page_count,
                score_note=SCORE_NOTE)
        return self._run(build)

    def recommendation(self, customer_id: str) -> s.RecommendationResponse:
        def build(f: RetentionFacade) -> s.RecommendationResponse:
            f.recommendation(customer_id)                                  # 404 early for unknown customers
            drivers = self._drivers(f.customer_features(customer_id))
            return s.RecommendationResponse.model_validate(asdict(f.recommendation(customer_id, drivers)))
        return self._run(build)

    def _drivers(self, features: dict[str, object]) -> list[Driver]:
        """Optional Phase 3 SHAP drivers via the existing adapter. Any failure degrades to 'not available'."""
        if self._adapter is None:
            return []
        try:
            explanation = self._adapter.explain(features)
        except Exception as exc:  # noqa: BLE001 - explainability is an optional enrichment
            logger.info("SHAP drivers unavailable for recommendation (%s)", type(exc).__name__)
            return []
        risk_up = [x for x in explanation.features if x.direction == "increases_churn"]
        return [Driver(x.source_feature, x.raw_value, x.shap_value, x.direction) for x in risk_up[:TOP_DRIVERS]]

    def actions(self) -> s.ActionsResponse:
        def build(f: RetentionFacade) -> s.ActionsResponse:
            portfolio = f.portfolio()
            return s.ActionsResponse(
                currency_code=portfolio.currency_code, currency_symbol=portfolio.currency_symbol,
                actions=[s.ActionOptionOut.model_validate(asdict(a)) for a in f.actions()])
        return self._run(build)

    def simulate(self, request: s.SimulateRequest) -> s.SimulateResponse:
        def build(f: RetentionFacade) -> s.SimulateResponse:
            specs = [ScenarioSpec(
                action_id=r.action_id, name=r.name, cost_override=r.cost_override,
                success_rate_override=r.success_rate_override, decision_filter=r.decision_filter,
                risk_bands=tuple(r.risk_bands), segment_ids=tuple(r.segment_ids),
                min_churn_probability=r.min_churn_probability, top_n=r.top_n, customer_ids=tuple(r.customer_ids))
                for r in request.scenarios]
            return s.SimulateResponse.model_validate(asdict(f.simulate(specs)))
        return self._run(build)

    # ---------------------------------------------------------------------------------------- campaigns
    def create_campaign(self, request: s.CampaignCreateRequest) -> s.CampaignOut:
        return self._run(lambda f: s.CampaignOut.model_validate(asdict(f.create_campaign(
            request.name, request.action_id, request.campaign_date, request.randomized, request.notes))))

    def list_campaigns(self) -> s.CampaignListResponse:
        return self._run(lambda f: s.CampaignListResponse(
            campaigns=[s.CampaignOut.model_validate(asdict(c)) for c in f.campaigns()]))

    def campaign(self, campaign_id: str) -> s.CampaignMetricsOut:
        return self._run(lambda f: s.CampaignMetricsOut.model_validate(asdict(f.campaign_metrics(campaign_id))))

    def assign(self, campaign_id: str, request: s.AssignRequest) -> s.AssignResponse:
        return self._run(lambda f: s.AssignResponse.model_validate(
            asdict(f.assign(campaign_id, request.customer_ids, request.group))))

    def record_outcomes(self, campaign_id: str, request: s.OutcomeRequest) -> s.OutcomeResponse:
        items = [NewOutcome(o.customer_id, o.outcome, o.actual_cost, o.actual_retained_revenue)
                 for o in request.outcomes]
        return self._run(lambda f: s.OutcomeResponse.model_validate(asdict(f.record_outcomes(campaign_id, items))))

    def analytics(self) -> s.AnalyticsResponse:
        return self._run(lambda f: s.AnalyticsResponse.model_validate(asdict(f.analytics())))

    def uplift_readiness(self) -> s.UpliftReadinessResponse:
        return self._run(lambda f: s.UpliftReadinessResponse.model_validate(asdict(f.uplift_readiness())))




def build_retention_service(settings: Settings, adapter: Phase15Port | None = None) -> RetentionService:
    """Composition helper used by ``create_app``. Performs no I/O: everything is created lazily on first request."""
    import os

    return RetentionService(settings, RetentionSettings.from_env(os.environ), adapter)


__all__ = ["RetentionService", "build_retention_service", "ESTIMATE_NOTE"]
