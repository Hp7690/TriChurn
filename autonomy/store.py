"""SQLite persistence for Phase 11 (standard library only; a file separate from the Phase 9 campaign database).

* Starts empty; the schema is created idempotently. ``audit_events`` is append-only (triggers abort UPDATE/DELETE).
* Status changes are conditional UPDATEs (``WHERE status = ?``) inside one transaction with their audit row, so a
  transition can happen exactly once even under concurrent requests.
* All SQL is parameterised; ``LIKE`` is never used on user input.
"""
from __future__ import annotations

import json
import sqlite3
import threading
import uuid
from collections.abc import Iterator, Sequence
from contextlib import contextmanager
from pathlib import Path
from typing import Any

from autonomy.errors import AutonomyConflictError
from autonomy.models import (
    AuditEvent,
    Feedback,
    Page,
    Recommendation,
    RiskEvent,
    SnapshotInfo,
    SnapshotRow,
)

SCHEMA_VERSION = 1
SCHEMA = """
CREATE TABLE IF NOT EXISTS schema_meta (key TEXT PRIMARY KEY, value TEXT NOT NULL);
CREATE TABLE IF NOT EXISTS snapshots (
    snapshot_id INTEGER PRIMARY KEY AUTOINCREMENT, fingerprint TEXT NOT NULL, created_at TEXT NOT NULL,
    customer_count INTEGER NOT NULL);
CREATE TABLE IF NOT EXISTS snapshot_customers (
    snapshot_id INTEGER NOT NULL REFERENCES snapshots(snapshot_id), customer_id TEXT NOT NULL,
    churn_probability REAL NOT NULL, risk_band TEXT NOT NULL, decision TEXT NOT NULL,
    PRIMARY KEY (snapshot_id, customer_id));
CREATE TABLE IF NOT EXISTS risk_events (
    event_id TEXT PRIMARY KEY, fingerprint TEXT NOT NULL UNIQUE, customer_id TEXT NOT NULL, event_type TEXT NOT NULL,
    from_band TEXT, to_band TEXT NOT NULL, probability_before REAL, probability_after REAL NOT NULL,
    detected_at TEXT NOT NULL, snapshot_id INTEGER NOT NULL, source TEXT NOT NULL,
    status TEXT NOT NULL DEFAULT 'new' CHECK (status IN ('new', 'resolved')));
CREATE TABLE IF NOT EXISTS recommendations (
    recommendation_id TEXT PRIMARY KEY, fingerprint TEXT NOT NULL UNIQUE, customer_id TEXT NOT NULL,
    category TEXT NOT NULL, action_id TEXT, action_name TEXT, reason TEXT NOT NULL, risk_band TEXT NOT NULL,
    churn_probability REAL NOT NULL, priority TEXT NOT NULL, source TEXT NOT NULL, rule_id TEXT NOT NULL,
    rules_version TEXT NOT NULL, confidence REAL, evidence_json TEXT NOT NULL,
    status TEXT NOT NULL CHECK (status IN ('pending','approved','rejected','executed','failed','cancelled')),
    created_at TEXT NOT NULL, updated_at TEXT NOT NULL);
CREATE TABLE IF NOT EXISTS audit_events (
    audit_id INTEGER PRIMARY KEY AUTOINCREMENT, event_type TEXT NOT NULL, recommendation_id TEXT, customer_id TEXT,
    from_status TEXT, to_status TEXT, actor TEXT NOT NULL, actor_authenticated INTEGER NOT NULL,
    detail TEXT NOT NULL, created_at TEXT NOT NULL);
CREATE TRIGGER IF NOT EXISTS audit_events_no_update BEFORE UPDATE ON audit_events
    BEGIN SELECT RAISE(ABORT, 'audit_events is append-only'); END;
CREATE TRIGGER IF NOT EXISTS audit_events_no_delete BEFORE DELETE ON audit_events
    BEGIN SELECT RAISE(ABORT, 'audit_events is append-only'); END;
CREATE TABLE IF NOT EXISTS feedback (
    feedback_id TEXT PRIMARY KEY, recommendation_id TEXT NOT NULL UNIQUE REFERENCES recommendations(recommendation_id),
    customer_id TEXT NOT NULL, recommended_action TEXT, approval_decision TEXT NOT NULL, campaign_id TEXT,
    outcome TEXT NOT NULL CHECK (outcome IN ('retained','churned','no_response')), outcome_at TEXT NOT NULL,
    data_source TEXT NOT NULL, observed INTEGER NOT NULL CHECK (observed = 1), recorded_by TEXT NOT NULL,
    recorded_at TEXT NOT NULL);
CREATE TABLE IF NOT EXISTS idempotency_keys (
    key TEXT NOT NULL, endpoint TEXT NOT NULL, request_hash TEXT NOT NULL, response_json TEXT NOT NULL,
    created_at TEXT NOT NULL, PRIMARY KEY (key, endpoint));
"""
REC_COLUMNS = ("recommendation_id, customer_id, category, action_id, action_name, reason, risk_band, "
               "churn_probability, priority, source, rule_id, rules_version, confidence, evidence_json, status, "
               "created_at, updated_at")


def _page(items: Sequence[Any], total: int, page: int, size: int) -> Page:
    return Page(tuple(items), total, page, size, max(1, -(-total // size)))


def _rec(r: sqlite3.Row) -> Recommendation:
    return Recommendation(
        r["recommendation_id"], r["customer_id"], r["category"], r["action_id"], r["action_name"], r["reason"],
        r["risk_band"], r["churn_probability"], r["priority"], r["source"], r["rule_id"], r["rules_version"],
        r["confidence"], json.loads(r["evidence_json"]), r["status"], r["created_at"], r["updated_at"])


class AutonomyStore:
    def __init__(self, db_path: str | Path):
        self._path = str(db_path)
        self._lock = threading.RLock()
        self._memory: sqlite3.Connection | None = None

    @contextmanager
    def _connect(self) -> Iterator[sqlite3.Connection]:
        with self._lock:
            if self._path == ":memory:":
                if self._memory is None:
                    self._memory = sqlite3.connect(":memory:", check_same_thread=False)
                conn, close = self._memory, False
            else:
                Path(self._path).parent.mkdir(parents=True, exist_ok=True)
                conn, close = sqlite3.connect(self._path, timeout=10), True
            conn.row_factory = sqlite3.Row
            conn.execute("PRAGMA foreign_keys = ON")
            try:
                conn.executescript(SCHEMA)
                conn.execute("INSERT OR IGNORE INTO schema_meta VALUES ('schema_version', ?)", (str(SCHEMA_VERSION),))
                yield conn
                conn.commit()
            except BaseException:
                conn.rollback()
                raise
            finally:
                if close:
                    conn.close()

    # ------------------------------------------------------------------------------------------- snapshots
    def latest_snapshot(self) -> SnapshotInfo | None:
        with self._connect() as c:
            r = c.execute("SELECT * FROM snapshots ORDER BY snapshot_id DESC LIMIT 1").fetchone()
        return None if r is None else SnapshotInfo(r["snapshot_id"], r["fingerprint"], r["created_at"],
                                                   r["customer_count"])

    def snapshot_rows(self, snapshot_id: int) -> dict[str, SnapshotRow]:
        with self._connect() as c:
            rows = c.execute("SELECT * FROM snapshot_customers WHERE snapshot_id = ?", (snapshot_id,)).fetchall()
        return {r["customer_id"]: SnapshotRow(r["customer_id"], r["churn_probability"], r["risk_band"], r["decision"])
                for r in rows}

    def save_snapshot(self, fingerprint: str, rows: Sequence[SnapshotRow], created_at: str) -> SnapshotInfo:
        with self._connect() as c:
            cur = c.execute("INSERT INTO snapshots (fingerprint, created_at, customer_count) VALUES (?, ?, ?)",
                            (fingerprint, created_at, len(rows)))
            sid = int(cur.lastrowid or 0)
            c.executemany("INSERT INTO snapshot_customers VALUES (?, ?, ?, ?, ?)",
                          [(sid, r.customer_id, r.churn_probability, r.risk_band, r.decision) for r in rows])
        return SnapshotInfo(sid, fingerprint, created_at, len(rows))

    # ----------------------------------------------------------------------------------------- risk events
    def add_events(self, events: Sequence[RiskEvent], fingerprints: Sequence[str]) -> int:
        added = 0
        with self._connect() as c:
            for e, fp in zip(events, fingerprints, strict=True):
                cur = c.execute(
                    "INSERT OR IGNORE INTO risk_events (event_id, fingerprint, customer_id, event_type, from_band, "
                    "to_band, probability_before, probability_after, detected_at, snapshot_id, source, status) "
                    "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
                    (e.event_id, fp, e.customer_id, e.event_type, e.from_band, e.to_band, e.probability_before,
                     e.probability_after, e.detected_at, e.snapshot_id, e.source, e.status))
                added += cur.rowcount
        return added

    def resolve_events(self, customer_ids: Sequence[str]) -> int:
        with self._connect() as c:
            return sum(c.execute("UPDATE risk_events SET status = 'resolved' WHERE customer_id = ? AND status = 'new'",
                                 (cid,)).rowcount for cid in customer_ids)

    def list_events(self, to_band: str | None, status: str | None, page: int, size: int) -> Page:
        where, params = ["1 = 1"], []
        if to_band:
            where.append("to_band = ?")
            params.append(to_band)
        if status:
            where.append("status = ?")
            params.append(status)
        clause = " AND ".join(where)
        with self._connect() as c:
            total = c.execute(f"SELECT COUNT(*) FROM risk_events WHERE {clause}", params).fetchone()[0]
            rows = c.execute(f"SELECT * FROM risk_events WHERE {clause} ORDER BY detected_at DESC, event_id "
                             "LIMIT ? OFFSET ?", [*params, size, (page - 1) * size]).fetchall()
        return _page([RiskEvent(r["event_id"], r["customer_id"], r["event_type"], r["from_band"], r["to_band"],
                                r["probability_before"], r["probability_after"], r["detected_at"], r["snapshot_id"],
                                r["source"], r["status"]) for r in rows], total, page, size)

    def event_counts(self) -> dict[str, int]:
        with self._connect() as c:
            return {r["k"]: r["n"] for r in c.execute(
                "SELECT to_band || ':' || status AS k, COUNT(*) AS n FROM risk_events GROUP BY k").fetchall()}

    # ---------------------------------------------------------------------------------- recommendations
    def add_recommendations(self, recs: Sequence[tuple[Recommendation, str]], actor: str, now: str) -> int:
        """Insert (recommendation, fingerprint) pairs; existing fingerprints are skipped. One audit row per insert."""
        added = 0
        with self._connect() as c:
            for r, fp in recs:
                cur = c.execute(
                    f"INSERT OR IGNORE INTO recommendations (fingerprint, {REC_COLUMNS}) "
                    "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
                    (fp, r.recommendation_id, r.customer_id, r.category, r.action_id, r.action_name, r.reason,
                     r.risk_band, r.churn_probability, r.priority, r.source, r.rule_id, r.rules_version, r.confidence,
                     json.dumps(r.evidence, sort_keys=True), r.status, r.created_at, r.updated_at))
                if cur.rowcount:
                    added += 1
                    c.execute("INSERT INTO audit_events (event_type, recommendation_id, customer_id, from_status, "
                              "to_status, actor, actor_authenticated, detail, created_at) VALUES "
                              "('recommendation_created', ?, ?, NULL, 'pending', ?, 0, ?, ?)",
                              (r.recommendation_id, r.customer_id, actor, f"{r.rule_id} {r.rules_version}", now))
        return added

    def get_recommendation(self, recommendation_id: str) -> Recommendation | None:
        with self._connect() as c:
            r = c.execute(f"SELECT {REC_COLUMNS} FROM recommendations WHERE recommendation_id = ?",
                          (recommendation_id,)).fetchone()
        return None if r is None else _rec(r)

    def list_recommendations(self, status: str | None, category: str | None, priority: str | None,
                             risk_band: str | None, customer_id: str | None, page: int, size: int) -> Page:
        where, params = ["1 = 1"], []
        for column, value in (("status", status), ("category", category), ("priority", priority),
                              ("risk_band", risk_band), ("customer_id", customer_id)):
            if value:
                where.append(f"{column} = ?")
                params.append(value)
        clause = " AND ".join(where)
        with self._connect() as c:
            total = c.execute(f"SELECT COUNT(*) FROM recommendations WHERE {clause}", params).fetchone()[0]
            rows = c.execute(f"SELECT {REC_COLUMNS} FROM recommendations WHERE {clause} "
                             "ORDER BY priority, churn_probability DESC, recommendation_id LIMIT ? OFFSET ?",
                             [*params, size, (page - 1) * size]).fetchall()
        return _page([_rec(r) for r in rows], total, page, size)

    def recommendation_counts(self) -> dict[str, dict[str, int]]:
        out: dict[str, dict[str, int]] = {"status": {}, "category": {}, "priority": {}}
        with self._connect() as c:
            for column in out:
                for r in c.execute(f"SELECT {column} AS k, COUNT(*) AS n FROM recommendations GROUP BY {column}"):
                    out[column][r["k"]] = r["n"]
        return out

    def pending_estimates(self) -> list[dict[str, Any]]:
        with self._connect() as c:
            return [json.loads(r["evidence_json"]) for r in c.execute(
                "SELECT evidence_json FROM recommendations WHERE status = 'pending'").fetchall()]

    def transition(self, recommendation_id: str, allowed_from: Sequence[str], to_status: str, actor: str,
                   authenticated: bool, detail: str, now: str) -> Recommendation:
        """Atomically move a recommendation to ``to_status`` and append the audit row, or raise a conflict."""
        with self._connect() as c:
            current = c.execute("SELECT status, customer_id FROM recommendations WHERE recommendation_id = ?",
                                (recommendation_id,)).fetchone()
            if current is None:
                raise AutonomyConflictError("Recommendation not found.")
            marks = ", ".join("?" for _ in allowed_from)
            cur = c.execute(f"UPDATE recommendations SET status = ?, updated_at = ? WHERE recommendation_id = ? "
                            f"AND status IN ({marks})", [to_status, now, recommendation_id, *allowed_from])
            if cur.rowcount != 1:
                raise AutonomyConflictError(f"A '{current['status']}' recommendation cannot become '{to_status}'.")
            c.execute("INSERT INTO audit_events (event_type, recommendation_id, customer_id, from_status, to_status, "
                      "actor, actor_authenticated, detail, created_at) "
                      "VALUES ('status_changed', ?, ?, ?, ?, ?, ?, ?, ?)",
                      (recommendation_id, current["customer_id"], current["status"], to_status, actor,
                       int(authenticated), detail, now))
        found = self.get_recommendation(recommendation_id)
        assert found is not None
        return found

    # ----------------------------------------------------------------------------------------------- audit
    def add_audit(self, event_type: str, recommendation_id: str | None, customer_id: str | None, actor: str,
                  authenticated: bool, detail: str, now: str, from_status: str | None = None,
                  to_status: str | None = None) -> None:
        with self._connect() as c:
            c.execute("INSERT INTO audit_events (event_type, recommendation_id, customer_id, from_status, to_status, "
                      "actor, actor_authenticated, detail, created_at) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)",
                      (event_type, recommendation_id, customer_id, from_status, to_status, actor,
                       int(authenticated), detail, now))

    def list_audit(self, event_type: str | None, recommendation_id: str | None, customer_id: str | None,
                   page: int, size: int) -> Page:
        where, params = ["1 = 1"], []
        for column, value in (("event_type", event_type), ("recommendation_id", recommendation_id),
                              ("customer_id", customer_id)):
            if value:
                where.append(f"{column} = ?")
                params.append(value)
        clause = " AND ".join(where)
        with self._connect() as c:
            total = c.execute(f"SELECT COUNT(*) FROM audit_events WHERE {clause}", params).fetchone()[0]
            rows = c.execute(f"SELECT * FROM audit_events WHERE {clause} ORDER BY audit_id DESC LIMIT ? OFFSET ?",
                             [*params, size, (page - 1) * size]).fetchall()
        return _page([AuditEvent(r["audit_id"], r["event_type"], r["recommendation_id"], r["customer_id"],
                                 r["from_status"], r["to_status"], r["actor"], bool(r["actor_authenticated"]),
                                 r["detail"], r["created_at"]) for r in rows], total, page, size)

    # ------------------------------------------------------------------------------------------- feedback
    def add_feedback(self, f: Feedback, now: str) -> None:
        with self._connect() as c:
            try:
                c.execute("INSERT INTO feedback VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
                          (f.feedback_id, f.recommendation_id, f.customer_id, f.recommended_action, f.approval_decision,
                           f.campaign_id, f.outcome, f.outcome_at, f.data_source, int(f.observed), f.recorded_by,
                           f.recorded_at))
            except sqlite3.IntegrityError as exc:
                raise AutonomyConflictError("Feedback has already been recorded for this recommendation.") from exc
            c.execute("INSERT INTO audit_events (event_type, recommendation_id, customer_id, from_status, to_status, "
                      "actor, actor_authenticated, detail, created_at) VALUES ('feedback_recorded', ?, ?, NULL, NULL, "
                      "?, 1, ?, ?)", (f.recommendation_id, f.customer_id, f.recorded_by, f.outcome, now))

    def list_feedback(self, page: int, size: int) -> Page:
        with self._connect() as c:
            total = c.execute("SELECT COUNT(*) FROM feedback").fetchone()[0]
            rows = c.execute("SELECT * FROM feedback ORDER BY recorded_at DESC, feedback_id LIMIT ? OFFSET ?",
                             (size, (page - 1) * size)).fetchall()
        return _page([Feedback(r["feedback_id"], r["recommendation_id"], r["customer_id"], r["recommended_action"],
                               r["approval_decision"], r["campaign_id"], r["outcome"], r["outcome_at"],
                               r["data_source"], bool(r["observed"]), r["recorded_by"], r["recorded_at"])
                      for r in rows], total, page, size)

    def feedback_stats(self) -> list[tuple[str | None, str, int]]:
        with self._connect() as c:
            return [(r["a"], r["o"], r["n"]) for r in c.execute(
                "SELECT recommended_action AS a, outcome AS o, COUNT(*) AS n FROM feedback GROUP BY a, o").fetchall()]

    # ------------------------------------------------------------------------------------- idempotency
    def get_idempotent(self, key: str, endpoint: str) -> tuple[str, str] | None:
        with self._connect() as c:
            r = c.execute("SELECT request_hash, response_json FROM idempotency_keys WHERE key = ? AND endpoint = ?",
                          (key, endpoint)).fetchone()
        return None if r is None else (r["request_hash"], r["response_json"])

    def put_idempotent(self, key: str, endpoint: str, request_hash: str, response_json: str, now: str) -> None:
        with self._connect() as c:
            c.execute("INSERT OR IGNORE INTO idempotency_keys VALUES (?, ?, ?, ?, ?)",
                      (key, endpoint, request_hash, response_json, now))

    def counts(self) -> dict[str, int]:
        tables = ("snapshots", "risk_events", "recommendations", "audit_events", "feedback")
        with self._connect() as c:
            return {t: c.execute(f"SELECT COUNT(*) FROM {t}").fetchone()[0] for t in tables}


def new_id(prefix: str) -> str:
    return f"{prefix}_{uuid.uuid4().hex[:12]}"
