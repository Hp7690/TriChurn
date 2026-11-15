"""Shared vocabulary for Phase 13: module statuses, dataset kinds, dataset schemas and validation reports.

Pure Python (standard library only). Nothing here reads files, trains a model or invents a value.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import StrEnum
from typing import Any


class ModuleStatus(StrEnum):
    """Availability of a Phase 13 module. BLOCKED_BY_MISSING_DATA is never converted into zeros or sample values."""

    AVAILABLE = "AVAILABLE"
    PARTIALLY_AVAILABLE = "PARTIALLY_AVAILABLE"
    BLOCKED_BY_MISSING_DATA = "BLOCKED_BY_MISSING_DATA"
    DISABLED = "DISABLED"
    VALIDATION_FAILED = "VALIDATION_FAILED"


class DatasetKind(StrEnum):
    FEEDBACK = "feedback"
    TICKETS = "tickets"
    NPS = "nps"
    CSAT = "csat"
    EVENTS = "events"


class ColumnType(StrEnum):
    STRING = "string"
    TEXT = "text"  # free text: formula-prefix warning applies
    TIMESTAMP = "timestamp"  # ISO 8601 date or date-time
    INTEGER = "integer"
    NUMBER = "number"
    CATEGORY = "category"  # value must belong to `allowed`
    JSON_OBJECT = "json_object"


class Severity(StrEnum):
    ERROR = "error"
    WARNING = "warning"


@dataclass(frozen=True)
class ColumnSpec:
    name: str
    type: ColumnType
    required: bool = True
    allowed: tuple[str, ...] = ()
    description: str = ""

    def to_dict(self) -> dict[str, Any]:
        return {
            "name": self.name,
            "type": self.type.value,
            "required": self.required,
            "allowed": list(self.allowed),
            "description": self.description,
        }


@dataclass(frozen=True)
class DatasetSchema:
    kind: DatasetKind
    columns: tuple[ColumnSpec, ...]
    customer_id_column: str = "customer_id"
    timestamp_columns: tuple[str, ...] = ()
    duplicate_key: tuple[str, ...] = ()  # columns that together identify one record
    description: str = ""

    @property
    def required_columns(self) -> tuple[str, ...]:
        return tuple(c.name for c in self.columns if c.required)

    @property
    def optional_columns(self) -> tuple[str, ...]:
        return tuple(c.name for c in self.columns if not c.required)

    def column(self, name: str) -> ColumnSpec | None:
        return next((c for c in self.columns if c.name == name), None)

    def to_dict(self) -> dict[str, Any]:
        return {
            "kind": self.kind.value,
            "description": self.description,
            "required_columns": list(self.required_columns),
            "optional_columns": list(self.optional_columns),
            "columns": [c.to_dict() for c in self.columns],
        }


@dataclass(frozen=True)
class ValidationIssue:
    """One problem. Messages never contain the offending cell value (privacy): only code, column and row number."""

    code: str
    severity: Severity
    message: str
    column: str | None = None
    row: int | None = None  # 1-based data row (header excluded); None = file or column level

    def to_dict(self) -> dict[str, Any]:
        return {
            "code": self.code,
            "severity": self.severity.value,
            "message": self.message,
            "column": self.column,
            "row": self.row,
        }


@dataclass
class ValidationReport:
    kind: str
    file_format: str
    valid: bool = False  # True only when there are zero ERROR issues and at least one record
    rows_total: int = 0
    rows_valid: int = 0  # rows with no ERROR issue
    error_count: int = 0
    warning_count: int = 0
    columns_found: list[str] = field(default_factory=list)
    missing_required_columns: list[str] = field(default_factory=list)
    unexpected_columns: list[str] = field(default_factory=list)
    issues: list[ValidationIssue] = field(default_factory=list)
    issue_counts: dict[str, int] = field(default_factory=dict)  # complete counts by code, even when truncated
    missing_value_counts: dict[str, int] = field(default_factory=dict)  # required AND optional columns
    duplicate_records: int = 0
    invalid_customer_ids: int = 0
    invalid_timestamps: int = 0
    out_of_order_records: int = 0
    unknown_customer_ids: int = 0
    issues_truncated: bool = False
    persisted: bool = False  # always False: uploads are validated in memory only

    def to_dict(self) -> dict[str, Any]:
        return {
            "kind": self.kind,
            "file_format": self.file_format,
            "valid": self.valid,
            "rows_total": self.rows_total,
            "rows_valid": self.rows_valid,
            "error_count": self.error_count,
            "warning_count": self.warning_count,
            "columns_found": list(self.columns_found),
            "missing_required_columns": list(self.missing_required_columns),
            "unexpected_columns": list(self.unexpected_columns),
            "issues": [i.to_dict() for i in self.issues],
            "issue_counts": dict(self.issue_counts),
            "missing_value_counts": dict(self.missing_value_counts),
            "duplicate_records": self.duplicate_records,
            "invalid_customer_ids": self.invalid_customer_ids,
            "invalid_timestamps": self.invalid_timestamps,
            "out_of_order_records": self.out_of_order_records,
            "unknown_customer_ids": self.unknown_customer_ids,
            "issues_truncated": self.issues_truncated,
            "persisted": self.persisted,
        }


class BlockedByMissingData(Exception):
    """Raised when an analytic is requested without the real dataset it needs. Callers report the blocked status."""

    def __init__(self, module: str, reason: str):
        super().__init__(reason)
        self.module, self.reason = module, reason


# ---------------------------------------------------------------------------------------------------------------
# Built-in dataset schemas: the contract a future real dataset must meet
# ---------------------------------------------------------------------------------------------------------------
def build_schemas(
    *,
    severities: tuple[str, ...] = ("low", "medium", "high", "critical"),
    statuses: tuple[str, ...] = ("open", "in_progress", "resolved", "closed"),
    sentiment_labels: tuple[str, ...] = ("positive", "neutral", "negative"),
) -> dict[DatasetKind, DatasetSchema]:
    C, T = ColumnSpec, ColumnType
    feedback = DatasetSchema(
        DatasetKind.FEEDBACK,
        (
            C("feedback_id", T.STRING, description="Unique id of the feedback record."),
            C("customer_id", T.STRING, description="Customer the feedback is from."),
            C("feedback_text", T.TEXT, description="The customer's own words."),
            C("submitted_at", T.TIMESTAMP, description="ISO 8601 date or date-time."),
            C("channel", T.STRING, required=False, description="For example email, chat or app."),
            C(
                "sentiment_label",
                T.CATEGORY,
                required=False,
                allowed=sentiment_labels,
                description="Human-assigned label. Needed only to train or evaluate a future sentiment model.",
            ),
        ),
        timestamp_columns=("submitted_at",),
        duplicate_key=("feedback_id",),
        description="Customer feedback with real text.",
    )
    tickets = DatasetSchema(
        DatasetKind.TICKETS,
        (
            C("ticket_id", T.STRING),
            C("customer_id", T.STRING),
            C("category", T.STRING, description="Ticket category as recorded by the support system."),
            C("severity", T.CATEGORY, allowed=severities),
            C("status", T.CATEGORY, allowed=statuses),
            C("created_at", T.TIMESTAMP),
            C("resolved_at", T.TIMESTAMP, required=False),
            C("sla_due_at", T.TIMESTAMP, required=False, description="SLA deadline; enables SLA analytics."),
        ),
        timestamp_columns=("created_at", "resolved_at", "sla_due_at"),
        duplicate_key=("ticket_id",),
        description="Complaint or support tickets from a real ticketing system.",
    )
    survey_cols = (
        C("response_id", T.STRING),
        C("customer_id", T.STRING),
        C("score", T.NUMBER, description="Survey score on the configured scale."),
        C("survey_date", T.TIMESTAMP),
    )
    nps = DatasetSchema(
        DatasetKind.NPS,
        survey_cols,
        timestamp_columns=("survey_date",),
        duplicate_key=("response_id",),
        description="NPS survey responses (0-10 by default).",
    )
    csat = DatasetSchema(
        DatasetKind.CSAT,
        survey_cols,
        timestamp_columns=("survey_date",),
        duplicate_key=("response_id",),
        description="CSAT survey responses (1-5 by default).",
    )
    events = DatasetSchema(
        DatasetKind.EVENTS,
        (
            C("customer_id", T.STRING),
            C("event_type", T.STRING),
            C("event_timestamp", T.TIMESTAMP),
            C("channel", T.STRING),
            C("event_id", T.STRING, required=False, description="Optional unique id; improves duplicate detection."),
            C("metadata", T.JSON_OBJECT, required=False, description="Optional JSON object."),
        ),
        timestamp_columns=("event_timestamp",),
        duplicate_key=("customer_id", "event_type", "event_timestamp", "channel"),
        description="Timestamped customer journey events: the only valid basis for a real journey.",
    )
    return {s.kind: s for s in (feedback, tickets, nps, csat, events)}
