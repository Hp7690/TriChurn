"""Retention prioritisation: a transparent, configurable HEURISTIC ranking.

    priority_score = 100 x ( w_var x pct(value_at_risk) + w_p x pct(churn_probability) + w_enb x pct(max(ENB, 0)) )

``pct`` is the average-rank percentile across the portfolio (0-1). Inputs are the locked Phase 2 probability and the
Phase 4 value at risk / ENB. The score is NOT a probability and is not validated against outcomes.

Ordering: Phase 4 intervention candidates first (score descending), then everyone else (score descending); ties are
broken by customer id so the order is deterministic.
"""
from __future__ import annotations

from dataclasses import dataclass

import pandas as pd

from retention.config import PriorityConfig
from retention.errors import RetentionInputError
from retention.models import INTERVENE, Portfolio, ScoredCustomer

TIER_P1, TIER_P2, TIER_P3, TIER_P4, TIER_MONITOR = "P1", "P2", "P3", "P4", "MONITOR"
TIERS = (TIER_P1, TIER_P2, TIER_P3, TIER_P4, TIER_MONITOR)

SORT_FIELDS = ("rank", "priority_score", "churn_probability", "value_at_risk", "clv", "expected_net_benefit")


@dataclass(frozen=True)
class PriorityComponents:
    value_at_risk_percentile: float
    churn_probability_percentile: float
    expected_net_benefit_percentile: float


@dataclass(frozen=True)
class PriorityEntry:
    rank: int
    customer: ScoredCustomer
    score: float
    tier: str
    components: PriorityComponents


@dataclass(frozen=True)
class PriorityFilter:
    search: str | None = None
    risk_band: str | None = None
    segment_id: int | None = None
    decision: str | None = None
    tier: str | None = None
    min_churn_probability: float | None = None


@dataclass(frozen=True)
class PriorityPage:
    items: tuple[PriorityEntry, ...]
    total: int
    page: int
    page_size: int
    page_count: int


def _tier(score: float, decision: str, cuts: tuple[float, float, float]) -> str:
    if decision != INTERVENE:
        return TIER_MONITOR
    if score >= cuts[0]:
        return TIER_P1
    if score >= cuts[1]:
        return TIER_P2
    if score >= cuts[2]:
        return TIER_P3
    return TIER_P4


class PriorityIndex:
    """Computed once per portfolio; all queries are in-memory and paginated."""

    def __init__(self, portfolio: Portfolio, config: PriorityConfig):
        self.portfolio = portfolio
        self.config = config
        self.entries: tuple[PriorityEntry, ...] = self._rank(portfolio, config)
        self._by_id = {e.customer.customer_id: e for e in self.entries}

    @staticmethod
    def _rank(portfolio: Portfolio, config: PriorityConfig) -> tuple[PriorityEntry, ...]:
        customers = portfolio.customers
        if not customers:
            return ()
        frame = pd.DataFrame({
            "var": [c.value_at_risk for c in customers],
            "p": [c.churn_probability for c in customers],
            "enb": [max(c.expected_net_benefit, 0.0) for c in customers]})
        pct = frame.rank(method="average", pct=True)
        scored = []
        for position, c in enumerate(customers):
            comp = PriorityComponents(float(pct.at[position, "var"]), float(pct.at[position, "p"]),
                                      float(pct.at[position, "enb"]))
            score = 100.0 * (config.weight_value_at_risk * comp.value_at_risk_percentile
                             + config.weight_churn_probability * comp.churn_probability_percentile
                             + config.weight_expected_net_benefit * comp.expected_net_benefit_percentile)
            scored.append((c, round(score, 4), comp))
        scored.sort(key=lambda t: (t[0].decision != INTERVENE, -t[1], t[0].customer_id))
        return tuple(PriorityEntry(i + 1, c, s, _tier(s, c.decision, config.tier_min_scores), comp)
                     for i, (c, s, comp) in enumerate(scored))

    def entry(self, customer_id: str) -> PriorityEntry | None:
        return self._by_id.get(customer_id)

    def query(self, flt: PriorityFilter | None = None, sort_by: str = "rank", descending: bool = False,
              page: int = 1, page_size: int = 25, max_page_size: int = 200) -> PriorityPage:
        flt = flt or PriorityFilter()
        if sort_by not in SORT_FIELDS:
            raise RetentionInputError(f"sort_by must be one of {', '.join(SORT_FIELDS)}.")
        if page < 1 or not 1 <= page_size <= max_page_size:
            raise RetentionInputError(f"page must be >= 1 and page_size between 1 and {max_page_size}.")
        if flt.tier is not None and flt.tier not in TIERS:
            raise RetentionInputError(f"tier must be one of {', '.join(TIERS)}.")
        if flt.min_churn_probability is not None and not 0.0 <= flt.min_churn_probability <= 1.0:
            raise RetentionInputError("min_churn_probability must be between 0 and 1.")
        needle = flt.search.strip().lower() if flt.search else ""
        rows = [e for e in self.entries
                if (not needle or needle in e.customer.customer_id.lower())
                and (flt.risk_band is None or e.customer.risk_band == flt.risk_band)
                and (flt.segment_id is None or e.customer.segment_id == flt.segment_id)
                and (flt.decision is None or e.customer.decision == flt.decision)
                and (flt.tier is None or e.tier == flt.tier)
                and (flt.min_churn_probability is None or e.customer.churn_probability >= flt.min_churn_probability)]
        if sort_by != "rank" or descending:
            rows.sort(key=lambda e: (_sort_value(e, sort_by), e.customer.customer_id), reverse=descending)
        total = len(rows)
        page_count = max(1, -(-total // page_size))
        start = (min(page, page_count) - 1) * page_size
        return PriorityPage(tuple(rows[start:start + page_size]), total, min(page, page_count), page_size, page_count)


def _sort_value(entry: PriorityEntry, key: str) -> float:
    c = entry.customer
    return {"rank": float(entry.rank), "priority_score": entry.score, "churn_probability": c.churn_probability,
            "value_at_risk": c.value_at_risk, "clv": c.clv, "expected_net_benefit": c.expected_net_benefit}[key]


def explain_priority(entry: PriorityEntry, portfolio: Portfolio) -> tuple[str, ...]:
    """Plain-language reasons built only from values already computed by the locked pipeline."""
    c, sym = entry.customer, portfolio.currency_symbol
    reasons = [
        f"Value at risk {sym}{c.value_at_risk:,.0f} is higher than "
        f"{entry.components.value_at_risk_percentile * 100:.0f}% of customers (CLV {sym}{c.clv:,.0f} x churn "
        f"probability {c.churn_probability:.1%}).",
        f"Churn probability {c.churn_probability:.1%} from the locked Phase 2 model ({c.risk_band} risk band).",
        f"Segment: {c.segment_name} (descriptive Phase 5 assignment)."]
    if c.decision == INTERVENE:
        reasons.append(
            f"Phase 4 decision: intervene with '{c.recommended_action}' - estimated net benefit "
            f"{sym}{c.expected_net_benefit:,.0f} under an ASSUMED {c.action_success_rate:.0%} success rate and "
            f"{sym}{c.action_cost:,.0f} cost.")
    else:
        reasons.extend(c.decision_reasons[:2] or ("Phase 4 decision: do not intervene.",))
    return tuple(reasons)
