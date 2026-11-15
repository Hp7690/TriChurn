"""Batch risk monitoring (NOT real-time streaming).

There is no live customer event source in TriChurn: the data is a static dataset scored by locked artifacts. A "scan"
stores a snapshot of the scored portfolio and compares it with the previous snapshot. The first scan is only a baseline
and creates no events. If the scoring inputs are unchanged since the last snapshot, nothing is stored (no duplicate
alerts). Events: risk_band_increase, probability_increase (>= configured change), decision_to_intervene, new_customer.
Earlier 'new' events for a customer are marked 'resolved' when the risk later falls back.
"""
from __future__ import annotations

import hashlib
from collections.abc import Callable
from dataclasses import dataclass

from autonomy.config import RISK_ORDER, AutonomyConfig
from autonomy.models import RiskEvent, SnapshotRow
from autonomy.store import AutonomyStore, new_id
from retention.models import INTERVENE, Portfolio

SOURCE = "batch_snapshot_comparison"


@dataclass(frozen=True)
class ScanResult:
    status: str                  # baseline | unchanged | compared
    snapshot_id: int
    previous_snapshot_id: int | None
    customers: int
    events_created: int
    events_resolved: int
    note: str


def portfolio_fingerprint(portfolio: Portfolio) -> str:
    raw = "|".join((portfolio.dataset_sha256, portfolio.model_sha256, portfolio.segmentation_sha256,
                    str(len(portfolio.customers))))
    return hashlib.sha256(raw.encode()).hexdigest()


def _rank(band: str) -> int:
    return RISK_ORDER.index(band) if band in RISK_ORDER else -1


def scan(portfolio: Portfolio, store: AutonomyStore, config: AutonomyConfig, now: Callable[[], str]) -> ScanResult:
    fp = portfolio_fingerprint(portfolio)
    previous = store.latest_snapshot()
    if previous is not None and previous.fingerprint == fp:
        return ScanResult("unchanged", previous.snapshot_id, previous.snapshot_id, previous.customer_count, 0, 0,
                          "The scored portfolio is identical to the last snapshot; no new snapshot or alerts.")
    rows = [SnapshotRow(c.customer_id, c.churn_probability, c.risk_band, c.decision) for c in portfolio.customers]
    stamp = now()
    before = store.snapshot_rows(previous.snapshot_id) if previous is not None else {}
    snap = store.save_snapshot(fp, rows, stamp)
    if previous is None:
        return ScanResult("baseline", snap.snapshot_id, None, len(rows), 0, 0,
                          "Baseline snapshot stored. Alerts appear only when a later scan finds a change.")

    events: list[RiskEvent] = []
    fingerprints: list[str] = []
    improved: list[str] = []

    def add(row: SnapshotRow, kind: str, prev: SnapshotRow | None) -> None:
        key = "|".join((row.customer_id, kind, prev.risk_band if prev else "-", row.risk_band,
                        str(previous.snapshot_id), str(snap.snapshot_id)))
        events.append(RiskEvent(new_id("evt"), row.customer_id, kind, prev.risk_band if prev else None, row.risk_band,
                                prev.churn_probability if prev else None, row.churn_probability, stamp,
                                snap.snapshot_id, SOURCE, "new"))
        fingerprints.append(hashlib.sha256(key.encode()).hexdigest())

    for row in rows:
        prev = before.get(row.customer_id)
        if prev is None:
            add(row, "new_customer", None)
            continue
        if _rank(row.risk_band) > _rank(prev.risk_band):
            add(row, "risk_band_increase", prev)
        elif row.churn_probability - prev.churn_probability >= config.min_probability_change:
            add(row, "probability_increase", prev)
        if row.decision == INTERVENE and prev.decision != INTERVENE:
            add(row, "decision_to_intervene", prev)
        if row.churn_probability < prev.churn_probability or _rank(row.risk_band) < _rank(prev.risk_band):
            improved.append(row.customer_id)
    created = store.add_events(events, fingerprints)
    resolved = store.resolve_events(improved) if improved else 0
    return ScanResult("compared", snap.snapshot_id, previous.snapshot_id, len(rows), created, resolved,
                      "Snapshot compared with the previous one.")
