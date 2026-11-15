"""Complaint intelligence foundation.

Provides the ticket category/severity/resolution vocabulary, a severity-classifier INTERFACE and an aggregation
service over REAL validated ticket rows. With no ticket rows it raises ``BlockedByMissingData``; it never returns
zero counts as if they were measurements and never generates synthetic tickets.
"""

from __future__ import annotations

import statistics
from collections import Counter
from collections.abc import Mapping, Sequence
from datetime import UTC, datetime
from typing import Any, Protocol, runtime_checkable

from trichurn_experience.config import ComplaintConfig
from trichurn_experience.schemas import BlockedByMissingData
from trichurn_experience.validation import parse_timestamp


@runtime_checkable
class SeverityClassifier(Protocol):
    """Interface for a future severity model. Phase 13 ships NO implementation and never guesses a severity."""

    def classify(self, ticket: Mapping[str, Any]) -> str: ...


def sla_state(ticket: Mapping[str, Any], cfg: ComplaintConfig, now: datetime) -> str:
    """One of: 'no_sla' (no deadline), 'met', 'breached', 'at_risk_open' (open and still inside the deadline)."""
    due = parse_timestamp(str(ticket.get("sla_due_at") or ""))
    if due is None:
        return "no_sla"
    resolved = parse_timestamp(str(ticket.get("resolved_at") or ""))
    status = str(ticket.get("status", "")).strip().lower()
    if resolved is not None and status in cfg.resolved_statuses:
        return "met" if resolved <= due else "breached"
    return "breached" if now > due else "at_risk_open"


def aggregate_complaints(
    tickets: Sequence[Mapping[str, Any]], cfg: ComplaintConfig, *, now: datetime | None = None
) -> dict[str, Any]:
    if not tickets:
        raise BlockedByMissingData("complaints", "There are no ticket records to aggregate.")
    now = now or datetime.now(UTC)
    by_category = Counter(str(t.get("category", "")).strip() or "Unspecified" for t in tickets)
    by_severity = Counter(str(t.get("severity", "")).strip().lower() for t in tickets)
    by_status = Counter(str(t.get("status", "")).strip().lower() for t in tickets)
    sla = Counter(sla_state(t, cfg, now) for t in tickets)
    hours: list[float] = []
    for t in tickets:
        created = parse_timestamp(str(t.get("created_at") or ""))
        resolved = parse_timestamp(str(t.get("resolved_at") or ""))
        if created and resolved and str(t.get("status", "")).strip().lower() in cfg.resolved_statuses:
            hours.append((resolved - created).total_seconds() / 3600.0)
    with_sla = sla["met"] + sla["breached"] + sla["at_risk_open"]
    decided = sla["met"] + sla["breached"]
    return {
        "tickets_total": len(tickets),
        "customers_with_tickets": len({str(t.get("customer_id", "")).strip() for t in tickets}),
        "by_category": dict(by_category.most_common()),
        "by_severity": {s: by_severity.get(s, 0) for s in cfg.severities},
        "by_status": {s: by_status.get(s, 0) for s in cfg.statuses},
        "resolution_hours": (
            {
                "count": len(hours),
                "median": round(statistics.median(hours), 2),
                "mean": round(statistics.fmean(hours), 2),
            }
            if hours
            else None
        ),
        "sla": {
            "tickets_with_sla": with_sla,
            "met": sla["met"],
            "breached": sla["breached"],
            "open_within_sla": sla["at_risk_open"],
            "no_sla_field": sla["no_sla"],
            "breach_rate_pct": round(100.0 * sla["breached"] / decided, 2) if decided else None,
        },
        "low_sample": len(tickets) < cfg.min_records,
        "min_records": cfg.min_records,
        "as_of": now.isoformat(),
    }
