"""Campaign performance analytics computed ONLY from recorded rows. ESTIMATED and ACTUAL figures are separate fields.

``observed_retention_rate`` is the share of recorded outcomes that were 'retained'. Without a control group it is an
OBSERVATION, not an uplift or causal effect, and each result says so.
"""
from __future__ import annotations

import math
from collections import defaultdict
from dataclasses import dataclass

from retention.campaign_store import AssignmentRecord, Campaign

OBSERVATION_NOTE = ("Observed figures come from outcomes recorded by users. Without a randomised control group they "
                    "describe what happened, not what the campaign caused (no uplift is claimed).")


@dataclass(frozen=True)
class CampaignMetrics:
    campaign_id: str
    name: str
    action_id: str
    campaign_date: str
    randomized: bool
    assigned: int
    outcomes_recorded: int
    outcome_coverage: float | None
    retained: int
    churned: int
    no_response: int
    observed_retention_rate: float | None      # retained / outcomes_recorded
    # --- ESTIMATES (Phase 4 snapshot taken at assignment time) ---
    estimated_cost: float
    estimated_benefit: float
    # --- ACTUALS (only what users recorded) ---
    actual_cost: float | None                  # None until at least one actual cost is recorded
    actual_retained_revenue: float | None
    actual_net_benefit: float | None           # only when both actual figures exist
    actual_roi: float | None
    note: str = OBSERVATION_NOTE


@dataclass(frozen=True)
class AnalyticsOverview:
    campaigns: tuple[CampaignMetrics, ...]
    total_assigned: int
    total_outcomes_recorded: int
    total_estimated_cost: float
    total_estimated_benefit: float
    total_actual_cost: float | None
    total_actual_retained_revenue: float | None
    note: str = OBSERVATION_NOTE


def _sum_or_none(values: list[float | None]) -> float | None:
    present = [v for v in values if v is not None]
    return round(math.fsum(present), 2) if present else None


def campaign_metrics(campaign: Campaign, rows: list[AssignmentRecord]) -> CampaignMetrics:
    recorded = [r for r in rows if r.outcome is not None]
    retained = sum(1 for r in recorded if r.outcome == "retained")
    actual_cost = _sum_or_none([r.actual_cost for r in recorded])
    actual_revenue = _sum_or_none([r.actual_retained_revenue for r in recorded])
    net = None if actual_cost is None or actual_revenue is None else round(actual_revenue - actual_cost, 2)
    return CampaignMetrics(
        campaign_id=campaign.campaign_id, name=campaign.name, action_id=campaign.action_id,
        campaign_date=campaign.campaign_date, randomized=campaign.randomized, assigned=len(rows),
        outcomes_recorded=len(recorded), outcome_coverage=round(len(recorded) / len(rows), 4) if rows else None,
        retained=retained, churned=sum(1 for r in recorded if r.outcome == "churned"),
        no_response=sum(1 for r in recorded if r.outcome == "no_response"),
        observed_retention_rate=round(retained / len(recorded), 4) if recorded else None,
        estimated_cost=round(math.fsum(r.estimated_cost for r in rows), 2),
        estimated_benefit=round(math.fsum(r.estimated_benefit for r in rows), 2),
        actual_cost=actual_cost, actual_retained_revenue=actual_revenue, actual_net_benefit=net,
        actual_roi=None if net is None or not actual_cost else round(net / actual_cost, 4))


def build_overview(campaigns: list[Campaign], assignments: list[AssignmentRecord]) -> AnalyticsOverview:
    by_campaign: dict[str, list[AssignmentRecord]] = defaultdict(list)
    for row in assignments:
        by_campaign[row.campaign_id].append(row)
    metrics = tuple(campaign_metrics(c, by_campaign.get(c.campaign_id, [])) for c in campaigns)
    return AnalyticsOverview(
        campaigns=metrics, total_assigned=sum(m.assigned for m in metrics),
        total_outcomes_recorded=sum(m.outcomes_recorded for m in metrics),
        total_estimated_cost=round(math.fsum(m.estimated_cost for m in metrics), 2),
        total_estimated_benefit=round(math.fsum(m.estimated_benefit for m in metrics), 2),
        total_actual_cost=_sum_or_none([m.actual_cost for m in metrics]),
        total_actual_retained_revenue=_sum_or_none([m.actual_retained_revenue for m in metrics]))
