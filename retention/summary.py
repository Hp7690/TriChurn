"""Executive retention summary: portfolio-level figures aggregated from per-customer Phase 2/4/5 results.

Figures for "recommended campaigns" assume the Phase 4 recommendation is applied to every intervention candidate.
They are ESTIMATES under assumed success rates (see ``ESTIMATE_NOTE``), not forecasts of actual outcomes.
"""
from __future__ import annotations

import math
from dataclasses import dataclass

from retention import ESTIMATE_NOTE, SCORE_NOTE
from retention.models import INTERVENE, Portfolio
from retention.prioritization import TIER_P1, TIER_P2, PriorityEntry, PriorityIndex

RISK_ORDER = ("LOW", "MEDIUM", "HIGH", "CRITICAL")


@dataclass(frozen=True)
class RiskBandSummary:
    risk_band: str
    customers: int
    value_at_risk: float
    total_clv: float


@dataclass(frozen=True)
class SegmentSummary:
    segment_id: int
    segment_name: str
    customers: int
    value_at_risk: float
    intervention_candidates: int
    average_churn_probability: float


@dataclass(frozen=True)
class CampaignEstimate:
    action_id: str
    action_name: str
    customers: int
    cost_per_customer: float
    assumed_success_rate: float
    estimated_total_cost: float
    estimated_retained_revenue: float
    estimated_net_benefit: float
    estimated_roi: float | None


@dataclass(frozen=True)
class ExecutiveSummary:
    currency_code: str
    currency_symbol: str
    total_customers: int
    average_churn_probability: float
    revenue_at_risk: float
    intervention_candidates: int
    high_priority_customers: int            # tiers P1 + P2
    high_priority_value_at_risk: float
    by_risk_band: tuple[RiskBandSummary, ...]
    by_segment: tuple[SegmentSummary, ...]
    recommended_campaigns: tuple[CampaignEstimate, ...]
    estimated_total_cost: float
    estimated_retained_revenue: float
    estimated_net_benefit: float
    estimated_roi: float | None
    top_priorities: tuple[PriorityEntry, ...]
    model_version: str
    segmentation_version: str
    dataset_sha256: str
    scored_at: str
    note: str = ESTIMATE_NOTE
    score_note: str = SCORE_NOTE


def build_summary(portfolio: Portfolio, index: PriorityIndex, top_n: int = 10) -> ExecutiveSummary:
    customers = portfolio.customers
    candidates = [c for c in customers if c.decision == INTERVENE]

    bands = []
    for band in RISK_ORDER:
        group = [c for c in customers if c.risk_band == band]
        bands.append(RiskBandSummary(band, len(group), round(math.fsum(c.value_at_risk for c in group), 2),
                                     round(math.fsum(c.clv for c in group), 2)))
    known = {b.risk_band for b in bands}
    for band in sorted({c.risk_band for c in customers} - known):           # tolerate reconfigured bands
        group = [c for c in customers if c.risk_band == band]
        bands.append(RiskBandSummary(band, len(group), round(math.fsum(c.value_at_risk for c in group), 2),
                                     round(math.fsum(c.clv for c in group), 2)))

    segments = []
    for sid in sorted({c.segment_id for c in customers}):
        group = [c for c in customers if c.segment_id == sid]
        segments.append(SegmentSummary(
            sid, group[0].segment_name, len(group), round(math.fsum(c.value_at_risk for c in group), 2),
            sum(1 for c in group if c.decision == INTERVENE),
            round(math.fsum(c.churn_probability for c in group) / len(group), 4)))

    campaigns = []
    for action in portfolio.action_catalogue:
        group = [c for c in candidates if c.recommended_action_id == action.action_id]
        if not group:
            continue
        cost = action.cost * len(group)
        benefit = math.fsum(c.expected_benefit for c in group)
        net = benefit - cost
        campaigns.append(CampaignEstimate(
            action.action_id, action.name, len(group), action.cost, action.success_rate, round(cost, 2),
            round(benefit, 2), round(net, 2), None if cost == 0 else round(net / cost, 4)))
    campaigns.sort(key=lambda e: (-e.estimated_net_benefit, e.action_id))

    total_cost = math.fsum(c.estimated_total_cost for c in campaigns)
    total_benefit = math.fsum(c.estimated_retained_revenue for c in campaigns)
    high = [e for e in index.entries if e.tier in (TIER_P1, TIER_P2)]
    return ExecutiveSummary(
        currency_code=portfolio.currency_code, currency_symbol=portfolio.currency_symbol,
        total_customers=len(customers),
        average_churn_probability=round(math.fsum(c.churn_probability for c in customers) / len(customers), 4)
        if customers else 0.0,
        revenue_at_risk=round(math.fsum(c.value_at_risk for c in customers), 2),
        intervention_candidates=len(candidates), high_priority_customers=len(high),
        high_priority_value_at_risk=round(math.fsum(e.customer.value_at_risk for e in high), 2),
        by_risk_band=tuple(bands), by_segment=tuple(segments), recommended_campaigns=tuple(campaigns),
        estimated_total_cost=round(total_cost, 2), estimated_retained_revenue=round(total_benefit, 2),
        estimated_net_benefit=round(total_benefit - total_cost, 2),
        estimated_roi=None if total_cost == 0 else round((total_benefit - total_cost) / total_cost, 4),
        top_priorities=index.entries[:top_n], model_version=portfolio.model_version,
        segmentation_version=portfolio.segmentation_version, dataset_sha256=portfolio.dataset_sha256,
        scored_at=portfolio.scored_at)
