"""Customer journey foundation: event sequences and aggregation over REAL timestamped events.

Tenure groups are NOT journeys and never pass through this module. With no validated events it raises
``BlockedByMissingData``.
"""

from __future__ import annotations

import statistics
from collections import Counter, defaultdict
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from datetime import datetime
from typing import Any

from trichurn_experience.schemas import BlockedByMissingData
from trichurn_experience.validation import parse_timestamp


@dataclass(frozen=True)
class JourneyEvent:
    customer_id: str
    event_type: str
    timestamp: datetime
    channel: str
    event_id: str | None = None
    metadata: Mapping[str, Any] | None = None


def to_events(rows: Sequence[Mapping[str, Any]]) -> list[JourneyEvent]:
    """Convert validated event rows. Rows with an unparseable timestamp are skipped (validation reports them)."""
    events: list[JourneyEvent] = []
    for row in rows:
        ts = parse_timestamp(str(row.get("event_timestamp", "")))
        cid = str(row.get("customer_id", "")).strip()
        if ts is None or not cid:
            continue
        meta = row.get("metadata")
        events.append(
            JourneyEvent(
                cid,
                str(row.get("event_type", "")).strip(),
                ts,
                str(row.get("channel", "")).strip(),
                (str(row["event_id"]).strip() or None) if row.get("event_id") else None,
                meta if isinstance(meta, dict) else None,
            )
        )
    return events


def deduplicate(events: Sequence[JourneyEvent]) -> tuple[list[JourneyEvent], int]:
    """Drop exact repeats (same event_id, else same customer/type/timestamp/channel). Returns (events, dropped)."""
    seen: set[tuple[Any, ...]] = set()
    kept: list[JourneyEvent] = []
    for e in events:
        key: tuple[Any, ...] = (
            ("id", e.event_id) if e.event_id else ("k", e.customer_id, e.event_type, e.timestamp, e.channel)
        )
        if key in seen:
            continue
        seen.add(key)
        kept.append(e)
    return kept, len(events) - len(kept)


def build_sequences(events: Sequence[JourneyEvent]) -> dict[str, list[JourneyEvent]]:
    """Customer -> events ordered by timestamp (stable: input order breaks ties)."""
    grouped: dict[str, list[tuple[int, JourneyEvent]]] = defaultdict(list)
    for i, e in enumerate(events):
        grouped[e.customer_id].append((i, e))
    return {cid: [e for _, e in sorted(items, key=lambda p: (p[1].timestamp, p[0]))] for cid, items in grouped.items()}


def customer_sequence(events: Sequence[JourneyEvent], customer_id: str) -> list[JourneyEvent]:
    """Interface for one customer's ordered sequence. Empty list when the customer has no events."""
    return build_sequences([e for e in events if e.customer_id == customer_id]).get(customer_id, [])


def aggregate_journeys(
    events: Sequence[JourneyEvent], *, min_events: int = 30, top_transitions: int = 10
) -> dict[str, Any]:
    if not events:
        raise BlockedByMissingData("journey", "There are no timestamped journey events to aggregate.")
    unique, dropped = deduplicate(events)
    sequences = build_sequences(unique)
    per_customer = [len(s) for s in sequences.values()]
    transitions: Counter[tuple[str, str]] = Counter()
    for seq in sequences.values():
        for a, b in zip(seq, seq[1:], strict=False):
            transitions[(a.event_type, b.event_type)] += 1
    stamps = [e.timestamp for e in unique]
    return {
        "events_total": len(unique),
        "duplicate_events_dropped": dropped,
        "customers": len(sequences),
        "events_per_customer": {
            "median": statistics.median(per_customer),
            "max": max(per_customer),
            "min": min(per_customer),
        },
        "by_event_type": dict(Counter(e.event_type for e in unique).most_common()),
        "by_channel": dict(Counter(e.channel for e in unique).most_common()),
        "top_transitions": [{"from": a, "to": b, "count": n} for (a, b), n in transitions.most_common(top_transitions)],
        "first_event": min(stamps).isoformat(),
        "last_event": max(stamps).isoformat(),
        "low_sample": len(unique) < min_events,
        "min_events": min_events,
    }
