"""Framework-free orchestration used by the API layer (and directly testable).

Raises only ``retention.errors`` exceptions. The API layer translates them to HTTP errors.
"""
from __future__ import annotations

import threading
from collections.abc import Sequence
from dataclasses import dataclass

from retention.analytics import AnalyticsOverview, CampaignMetrics, build_overview, campaign_metrics
from retention.campaign_store import (
    GROUPS,
    Campaign,
    CampaignStore,
    NewAssignment,
    NewOutcome,
)
from retention.config import RetentionConfig
from retention.errors import PortfolioUnavailableError, RetentionInputError, RetentionNotFoundError
from retention.models import NO_ACTION_ID, ActionOption, Portfolio
from retention.prioritization import PriorityFilter, PriorityIndex, PriorityPage, explain_priority
from retention.recommendation import Driver, Recommendation, recommend
from retention.scoring import PortfolioProvider
from retention.simulator import ScenarioComparison, ScenarioSpec, compare_scenarios
from retention.summary import ExecutiveSummary, build_summary
from retention.uplift_readiness import UpliftReadiness, assess


@dataclass(frozen=True)
class AssignmentReport:
    campaign_id: str
    requested: int
    assigned: int
    unknown_customer_ids: tuple[str, ...]
    ineligible_customer_ids: tuple[str, ...]
    already_assigned_ids: tuple[str, ...]


@dataclass(frozen=True)
class OutcomeReport:
    campaign_id: str
    requested: int
    recorded: int
    not_assigned_ids: tuple[str, ...]
    already_recorded_ids: tuple[str, ...]


class RetentionFacade:
    def __init__(self, provider: PortfolioProvider, store: CampaignStore, config: RetentionConfig):
        self._provider, self._store, self._config = provider, store, config
        self._lock = threading.Lock()
        self._index: PriorityIndex | None = None

    # ----------------------------------------------------------------------------------------- portfolio
    def portfolio(self) -> Portfolio:
        return self._provider.get()

    def index(self) -> PriorityIndex:
        portfolio = self._provider.get()
        with self._lock:
            if self._index is None or self._index.portfolio is not portfolio:
                self._index = PriorityIndex(portfolio, self._config.priority)
            return self._index

    def actions(self) -> tuple[ActionOption, ...]:
        return tuple(a for a in self.portfolio().action_catalogue if a.action_id != NO_ACTION_ID)

    # --------------------------------------------------------------------------------------- read models
    def summary(self) -> ExecutiveSummary:
        return build_summary(self.portfolio(), self.index())

    def priorities(self, flt: PriorityFilter, sort_by: str, descending: bool, page: int, page_size: int
                   ) -> tuple[PriorityPage, dict[str, tuple[str, ...]]]:
        result = self.index().query(flt, sort_by, descending, page, page_size)
        portfolio = self.portfolio()
        return result, {e.customer.customer_id: explain_priority(e, portfolio) for e in result.items}

    def recommendation(self, customer_id: str, drivers: Sequence[Driver] | None = None) -> Recommendation:
        entry = self.index().entry(customer_id)
        if entry is None:
            raise RetentionNotFoundError("Customer not found in the scored portfolio.")
        return recommend(entry.customer, self.portfolio(), entry, drivers)

    def customer_features(self, customer_id: str) -> dict[str, object]:
        customer = self.portfolio().get(customer_id)
        if customer is None:
            raise RetentionNotFoundError("Customer not found in the scored portfolio.")
        return dict(customer.features)

    def simulate(self, specs: Sequence[ScenarioSpec]) -> ScenarioComparison:
        sim = self._config.simulator
        return compare_scenarios(specs, self.portfolio(), self.index(), sim.max_scenarios, sim.max_target_customers)

    # ------------------------------------------------------------------------------------------ campaigns
    def create_campaign(self, name: str, action_id: str, campaign_date: str, randomized: bool,
                        notes: str | None) -> Campaign:
        known = {a.action_id: a for a in self.actions()}
        if action_id not in known or not known[action_id].eligible:        # catalogue ``eligible`` = enabled
            raise RetentionInputError("action_id is not an enabled Phase 4 retention action.")
        return self._store.create_campaign(name, action_id, campaign_date, randomized, notes)

    def assign(self, campaign_id: str, customer_ids: Sequence[str], group: str) -> AssignmentReport:
        if group not in GROUPS:
            raise RetentionInputError(f"group must be one of {', '.join(GROUPS)}.")
        cap = self._config.campaigns.max_customers_per_request
        unique = list(dict.fromkeys(customer_ids))
        if not unique:
            raise RetentionInputError("At least one customer id is required.")
        if len(unique) > cap:
            raise RetentionInputError(f"At most {cap} customers can be assigned per request.")
        campaign = self._store.get_campaign(campaign_id)
        portfolio = self.portfolio()
        accepted: list[NewAssignment] = []
        unknown: list[str] = []
        ineligible: list[str] = []
        for cid in unique:
            customer = portfolio.get(cid)
            if customer is None:
                unknown.append(cid)
                continue
            option = next((o for o in customer.options if o.action_id == campaign.action_id), None)
            if group == "control":      # controls receive nothing, so no cost or benefit is estimated for them
                accepted.append(NewAssignment(cid, 0.0, 0.0, customer.churn_probability, group))
            elif option is None or not option.eligible:
                ineligible.append(cid)
            else:
                accepted.append(NewAssignment(cid, option.cost, option.expected_benefit,
                                              customer.churn_probability, group))
        inserted, duplicates = self._store.assign(campaign_id, accepted)
        return AssignmentReport(campaign_id, len(unique), inserted, tuple(unknown), tuple(ineligible),
                                tuple(duplicates))

    def record_outcomes(self, campaign_id: str, outcomes: Sequence[NewOutcome]) -> OutcomeReport:
        cap = self._config.campaigns.max_customers_per_request
        if not outcomes:
            raise RetentionInputError("At least one outcome is required.")
        if len(outcomes) > cap:
            raise RetentionInputError(f"At most {cap} outcomes can be recorded per request.")
        recorded, missing, repeated = self._store.record_outcomes(campaign_id, outcomes)
        return OutcomeReport(campaign_id, len(outcomes), recorded, tuple(missing), tuple(repeated))

    def campaigns(self) -> list[Campaign]:
        return self._store.list_campaigns()

    def campaign_metrics(self, campaign_id: str) -> CampaignMetrics:
        campaign = self._store.get_campaign(campaign_id)
        return campaign_metrics(campaign, self._store.assignments(campaign_id))

    def analytics(self) -> AnalyticsOverview:
        return build_overview(self._store.list_campaigns(), self._store.assignments())

    def uplift_readiness(self) -> UpliftReadiness:
        try:
            columns: tuple[str, ...] | None = self.portfolio().dataset_columns
        except PortfolioUnavailableError:          # campaign evidence can still be assessed without the dataset
            columns = None
        return assess(columns, self._store.list_campaigns(), self._store.assignments(), self._config.uplift)
