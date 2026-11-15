"""Campaign tracking in SQLite (standard library only).

* The database STARTS EMPTY: the schema is created on first use and nothing is ever seeded.
* ESTIMATED figures (snapshot of the Phase 4 estimate when a customer is assigned) and ACTUAL figures (recorded by
  users after the fact) live in separate columns/tables and are never mixed or back-filled.
* All SQL is parameterised. Each operation runs in its own transaction on a short-lived connection.
"""
from __future__ import annotations

import math
import sqlite3
import threading
import uuid
from collections.abc import Iterator, Sequence
from contextlib import contextmanager
from dataclasses import dataclass
from datetime import UTC, date, datetime
from pathlib import Path

from retention.errors import RetentionInputError, RetentionNotFoundError

OUTCOMES = ("retained", "churned", "no_response")
GROUPS = ("treatment", "control", "unspecified")
MAX_TEXT = 500

SCHEMA = """
CREATE TABLE IF NOT EXISTS campaigns (
    campaign_id    TEXT PRIMARY KEY,
    name           TEXT NOT NULL,
    action_id      TEXT NOT NULL,
    campaign_date  TEXT NOT NULL,
    randomized     INTEGER NOT NULL DEFAULT 0 CHECK (randomized IN (0, 1)),
    notes          TEXT,
    created_at     TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS assignments (
    assignment_id          INTEGER PRIMARY KEY AUTOINCREMENT,
    campaign_id            TEXT NOT NULL REFERENCES campaigns(campaign_id),
    customer_id            TEXT NOT NULL,
    assignment_group       TEXT NOT NULL DEFAULT 'unspecified'
                           CHECK (assignment_group IN ('treatment', 'control', 'unspecified')),
    assigned_at            TEXT NOT NULL,
    estimated_cost         REAL NOT NULL,
    estimated_benefit      REAL NOT NULL,
    estimated_churn_probability REAL NOT NULL,
    UNIQUE (campaign_id, customer_id)
);
CREATE TABLE IF NOT EXISTS outcomes (
    assignment_id           INTEGER PRIMARY KEY REFERENCES assignments(assignment_id),
    outcome                 TEXT NOT NULL CHECK (outcome IN ('retained', 'churned', 'no_response')),
    actual_cost             REAL,
    actual_retained_revenue REAL,
    recorded_at             TEXT NOT NULL
);
"""


@dataclass(frozen=True)
class Campaign:
    campaign_id: str
    name: str
    action_id: str
    campaign_date: str
    randomized: bool
    notes: str | None
    created_at: str


@dataclass(frozen=True)
class AssignmentRecord:
    assignment_id: int
    campaign_id: str
    customer_id: str
    assignment_group: str
    assigned_at: str
    estimated_cost: float
    estimated_benefit: float
    estimated_churn_probability: float
    outcome: str | None
    actual_cost: float | None
    actual_retained_revenue: float | None
    outcome_recorded_at: str | None


@dataclass(frozen=True)
class NewAssignment:
    customer_id: str
    estimated_cost: float
    estimated_benefit: float
    estimated_churn_probability: float
    group: str = "unspecified"


@dataclass(frozen=True)
class NewOutcome:
    customer_id: str
    outcome: str
    actual_cost: float | None = None
    actual_retained_revenue: float | None = None


def _clean_text(value: str | None, name: str, required: bool = False) -> str | None:
    if value is None or not value.strip():
        if required:
            raise RetentionInputError(f"{name} is required.")
        return None
    value = value.strip()
    if len(value) > MAX_TEXT or any(ord(ch) < 32 for ch in value):
        raise RetentionInputError(f"{name} is too long or contains control characters.")
    return value


def _money(value: float | None, name: str) -> float | None:
    if value is None:
        return None
    if isinstance(value, bool) or not isinstance(value, int | float) or not math.isfinite(value) or value < 0:
        raise RetentionInputError(f"{name} must be a finite number >= 0.")
    return float(value)


def _probability(value: float, name: str) -> float:
    if (isinstance(value, bool) or not isinstance(value, int | float) or not math.isfinite(value)
            or not 0 <= value <= 1):
        raise RetentionInputError(f"{name} must be a finite number between 0 and 1.")
    return float(value)


class CampaignStore:
    """``db_path`` may be ``':memory:'`` (tests); a file path is created, with parent folders, on first use."""

    def __init__(self, db_path: str | Path):
        self._path = str(db_path)
        self._lock = threading.RLock()
        self._memory: sqlite3.Connection | None = None
        self._ready = False

    # ------------------------------------------------------------------------------------- connections
    @contextmanager
    def _connect(self) -> Iterator[sqlite3.Connection]:
        with self._lock:
            if self._path == ":memory:":
                if self._memory is None:
                    self._memory = sqlite3.connect(":memory:", check_same_thread=False)
                conn, close = self._memory, False
            else:
                if not self._ready:
                    Path(self._path).parent.mkdir(parents=True, exist_ok=True)
                conn, close = sqlite3.connect(self._path, timeout=10), True
            conn.row_factory = sqlite3.Row
            conn.execute("PRAGMA foreign_keys = ON")
            try:
                conn.executescript(SCHEMA)          # idempotent (IF NOT EXISTS): the database starts empty
                self._ready = True
                yield conn
                conn.commit()
            except BaseException:
                conn.rollback()
                raise
            finally:
                if close:
                    conn.close()

    # -------------------------------------------------------------------------------------- campaigns
    def create_campaign(self, name: str, action_id: str, campaign_date: str, randomized: bool = False,
                        notes: str | None = None, now: datetime | None = None) -> Campaign:
        clean_name = _clean_text(name, "name", required=True)
        clean_notes = _clean_text(notes, "notes")
        try:
            parsed = date.fromisoformat(campaign_date)
        except (TypeError, ValueError) as exc:
            raise RetentionInputError("campaign_date must be an ISO date (YYYY-MM-DD).") from exc
        if parsed.isoformat() != campaign_date:
            raise RetentionInputError("campaign_date must be an ISO date (YYYY-MM-DD).")
        if not 2000 <= parsed.year <= 2100:
            raise RetentionInputError("campaign_date is out of the supported range.")
        campaign = Campaign(f"cmp_{uuid.uuid4().hex[:12]}", clean_name or "", action_id, parsed.isoformat(),
                            bool(randomized), clean_notes, (now or datetime.now(UTC)).isoformat(timespec="seconds"))
        with self._connect() as conn:
            conn.execute("INSERT INTO campaigns VALUES (?, ?, ?, ?, ?, ?, ?)",
                         (campaign.campaign_id, campaign.name, campaign.action_id, campaign.campaign_date,
                          int(campaign.randomized), campaign.notes, campaign.created_at))
        return campaign

    @staticmethod
    def _campaign(row: sqlite3.Row) -> Campaign:
        return Campaign(row["campaign_id"], row["name"], row["action_id"], row["campaign_date"],
                        bool(row["randomized"]), row["notes"], row["created_at"])

    def get_campaign(self, campaign_id: str) -> Campaign:
        with self._connect() as conn:
            row = conn.execute("SELECT * FROM campaigns WHERE campaign_id = ?", (campaign_id,)).fetchone()
        if row is None:
            raise RetentionNotFoundError("Campaign not found.")
        return self._campaign(row)

    def list_campaigns(self) -> list[Campaign]:
        with self._connect() as conn:
            rows = conn.execute("SELECT * FROM campaigns ORDER BY campaign_date DESC, campaign_id").fetchall()
        return [self._campaign(r) for r in rows]

    # ------------------------------------------------------------------------------------ assignments
    def assign(self, campaign_id: str, items: Sequence[NewAssignment], now: datetime | None = None
               ) -> tuple[int, list[str]]:
        """Insert assignments atomically. Returns (inserted, already_assigned_ids); duplicates are reported, not
        silently overwritten, and the rest are still inserted."""
        stamp = (now or datetime.now(UTC)).isoformat(timespec="seconds")
        for item in items:
            if item.group not in GROUPS:
                raise RetentionInputError(f"group must be one of {', '.join(GROUPS)}.")
            _money(item.estimated_cost, "estimated_cost")
            _money(item.estimated_benefit, "estimated_benefit")
            _probability(item.estimated_churn_probability, "estimated_churn_probability")
        inserted, duplicates = 0, []
        with self._connect() as conn:
            if conn.execute("SELECT 1 FROM campaigns WHERE campaign_id = ?", (campaign_id,)).fetchone() is None:
                raise RetentionNotFoundError("Campaign not found.")
            for item in items:
                try:
                    conn.execute(
                        "INSERT INTO assignments (campaign_id, customer_id, assignment_group, assigned_at, "
                        "estimated_cost, estimated_benefit, estimated_churn_probability) VALUES (?, ?, ?, ?, ?, ?, ?)",
                        (campaign_id, item.customer_id, item.group, stamp, item.estimated_cost,
                         item.estimated_benefit, item.estimated_churn_probability))
                    inserted += 1
                except sqlite3.IntegrityError:
                    duplicates.append(item.customer_id)
        return inserted, duplicates

    # --------------------------------------------------------------------------------------- outcomes
    def record_outcomes(self, campaign_id: str, items: Sequence[NewOutcome], now: datetime | None = None
                        ) -> tuple[int, list[str], list[str]]:
        """Returns (recorded, not_assigned_ids, already_recorded_ids). An outcome is recorded once per assignment;
        corrections are deliberately not supported so the history cannot be silently rewritten."""
        stamp = (now or datetime.now(UTC)).isoformat(timespec="seconds")
        for item in items:
            if item.outcome not in OUTCOMES:
                raise RetentionInputError(f"outcome must be one of {', '.join(OUTCOMES)}.")
            _money(item.actual_cost, "actual_cost")
            revenue = _money(item.actual_retained_revenue, "actual_retained_revenue")
            if revenue is not None and item.outcome != "retained":
                raise RetentionInputError("actual_retained_revenue can only be recorded for a 'retained' outcome.")
        recorded, missing, repeated = 0, [], []
        with self._connect() as conn:
            if conn.execute("SELECT 1 FROM campaigns WHERE campaign_id = ?", (campaign_id,)).fetchone() is None:
                raise RetentionNotFoundError("Campaign not found.")
            for item in items:
                row = conn.execute("SELECT assignment_id FROM assignments WHERE campaign_id = ? AND customer_id = ?",
                                   (campaign_id, item.customer_id)).fetchone()
                if row is None:
                    missing.append(item.customer_id)
                    continue
                try:
                    conn.execute("INSERT INTO outcomes VALUES (?, ?, ?, ?, ?)",
                                 (row["assignment_id"], item.outcome, item.actual_cost,
                                  item.actual_retained_revenue, stamp))
                    recorded += 1
                except sqlite3.IntegrityError:
                    repeated.append(item.customer_id)
        return recorded, missing, repeated

    # ---------------------------------------------------------------------------------------- queries
    def assignments(self, campaign_id: str | None = None) -> list[AssignmentRecord]:
        sql = ("SELECT a.*, o.outcome, o.actual_cost, o.actual_retained_revenue, o.recorded_at AS outcome_recorded_at "
               "FROM assignments a LEFT JOIN outcomes o ON o.assignment_id = a.assignment_id")
        params: tuple[str, ...] = ()
        if campaign_id is not None:
            sql += " WHERE a.campaign_id = ?"
            params = (campaign_id,)
        with self._connect() as conn:
            rows = conn.execute(sql + " ORDER BY a.assignment_id", params).fetchall()
        return [AssignmentRecord(
            r["assignment_id"], r["campaign_id"], r["customer_id"], r["assignment_group"], r["assigned_at"],
            r["estimated_cost"], r["estimated_benefit"], r["estimated_churn_probability"], r["outcome"],
            r["actual_cost"], r["actual_retained_revenue"], r["outcome_recorded_at"]) for r in rows]

    def counts(self) -> dict[str, int]:
        with self._connect() as conn:
            return {
                "campaigns": conn.execute("SELECT COUNT(*) FROM campaigns").fetchone()[0],
                "assignments": conn.execute("SELECT COUNT(*) FROM assignments").fetchone()[0],
                "outcomes": conn.execute("SELECT COUNT(*) FROM outcomes").fetchone()[0]}
