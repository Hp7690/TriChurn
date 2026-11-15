"""Safe, in-memory validation of feedback, ticket, survey and event files (CSV or JSON).

Safety properties (all covered by tests):
* Content is only PARSED (``csv`` / ``json`` from the standard library). Nothing is evaluated, imported or executed.
* Size, row, column and field limits are enforced before and during parsing.
* Files are never written. ``ValidationReport.persisted`` is always False.
* Issue messages carry the row number and column name but never the cell value.
* ``resolve_safe_path`` rejects absolute paths, ``..`` traversal, NUL bytes and symlink escapes for configured files.
"""

from __future__ import annotations

import csv
import io
import json
import math
import re
from collections import Counter
from collections.abc import Iterable, Mapping
from dataclasses import dataclass
from datetime import UTC, date, datetime, timedelta
from pathlib import Path
from typing import Any

from trichurn_experience.config import ExperienceConfig
from trichurn_experience.schemas import (
    ColumnType,
    DatasetKind,
    DatasetSchema,
    Severity,
    ValidationIssue,
    ValidationReport,
    build_schemas,
)

FORMULA_PREFIXES = ("=", "+", "-", "@", "\t", "\r")
SUPPORTED_FORMATS = ("csv", "json")


class PayloadTooLarge(ValueError):
    """The submitted content exceeds a configured limit (bytes, rows or columns)."""


class UnsafePath(ValueError):
    """A configured dataset path escapes the allowed data directory or has an unsupported type."""


class UnreadableContent(ValueError):
    """The content cannot be parsed as the declared format. Never includes content in its message."""


# ------------------------------------------------------------------------------------------------ timestamps
def parse_timestamp(value: str) -> datetime | None:
    """Parse an ISO 8601 date or date-time. Returns a timezone-aware UTC datetime (naive values are taken as UTC)."""
    text = value.strip()
    if not text or len(text) > 40:
        return None
    try:
        if re.fullmatch(r"\d{4}-\d{2}-\d{2}", text):
            return datetime.combine(date.fromisoformat(text), datetime.min.time(), tzinfo=UTC)
        parsed = datetime.fromisoformat(text)
    except ValueError:
        return None
    return parsed.replace(tzinfo=UTC) if parsed.tzinfo is None else parsed.astimezone(UTC)


# ------------------------------------------------------------------------------------------------ safe paths
def resolve_safe_path(base_dir: Path, relative: str, *, allowed_suffixes: tuple[str, ...] = (".csv", ".json")) -> Path:
    """Resolve ``relative`` strictly inside ``base_dir``. Raises ``UnsafePath`` otherwise."""
    if not isinstance(relative, str) or not relative or "\x00" in relative:
        raise UnsafePath("The dataset path is empty or contains invalid characters.")
    candidate = Path(relative)
    if candidate.is_absolute() or relative.startswith(("/", "\\")) or re.match(r"^[A-Za-z]:", relative):
        raise UnsafePath("Dataset paths must be relative to the experience data directory.")
    if ".." in candidate.parts or ".." in Path(relative.replace("\\", "/")).parts:
        raise UnsafePath("Dataset paths must not contain '..'.")
    if candidate.suffix.lower() not in allowed_suffixes:
        raise UnsafePath("Only .csv and .json dataset files are supported.")
    base = base_dir.resolve()
    resolved = (base / candidate).resolve()
    try:
        resolved.relative_to(base)
    except ValueError as exc:
        raise UnsafePath("The dataset path resolves outside the experience data directory.") from exc
    return resolved


# ------------------------------------------------------------------------------------------------ parsing
@dataclass
class ParsedRecords:
    columns: list[str]
    rows: list[dict[str, Any]]
    file_issues: list[ValidationIssue]


def _decode(data: bytes | str, max_bytes: int) -> str:
    raw = data.encode("utf-8") if isinstance(data, str) else data
    if len(raw) > max_bytes:
        raise PayloadTooLarge("The content exceeds the configured size limit.")
    if b"\x00" in raw:
        raise UnreadableContent("The content contains NUL bytes and is not a text file.")
    try:
        return raw.decode("utf-8-sig")
    except UnicodeDecodeError as exc:
        raise UnreadableContent("The content is not valid UTF-8 text.") from exc


def _parse_csv(text: str, cfg: ExperienceConfig) -> ParsedRecords:
    limits = cfg.limits
    reader = csv.reader(io.StringIO(text, newline=""), strict=False)
    try:
        header = next(reader)
    except StopIteration:
        raise UnreadableContent("The CSV content is empty.") from None
    except csv.Error as exc:
        raise UnreadableContent("The CSV header could not be parsed.") from exc
    header = [h.strip() for h in header]
    if len(header) > limits.max_columns:
        raise PayloadTooLarge("The CSV has more columns than the configured limit.")
    issues: list[ValidationIssue] = []
    blanks = [i for i, h in enumerate(header) if not h]
    if blanks:
        issues.append(ValidationIssue("blank_column_name", Severity.ERROR, "The header contains a blank column name."))
    dup_cols = [name for name, n in Counter(h for h in header if h).items() if n > 1]
    for name in dup_cols:
        issues.append(
            ValidationIssue("duplicate_column", Severity.ERROR, "A column name appears more than once.", name)
        )
    rows: list[dict[str, Any]] = []
    try:
        for line in reader:
            if not line or all(cell == "" for cell in line):
                continue  # blank lines are skipped, not counted
            if len(rows) >= limits.max_rows:
                raise PayloadTooLarge("The CSV has more rows than the configured limit.")
            if any(len(cell) > limits.max_field_chars for cell in line):
                rows.append({"__oversized__": True})
                continue
            if len(line) != len(header):
                rows.append({"__ragged__": True})
                continue
            rows.append(dict(zip(header, line, strict=True)))
    except csv.Error as exc:
        raise UnreadableContent("The CSV content could not be parsed.") from exc
    return ParsedRecords(header, rows, issues)


def _reject_constant(_name: str) -> Any:
    raise ValueError("NaN and Infinity are not valid JSON values.")


def _parse_json(text: str, cfg: ExperienceConfig) -> ParsedRecords:
    limits = cfg.limits
    try:
        payload = json.loads(text, parse_constant=_reject_constant)
    except (ValueError, RecursionError) as exc:
        raise UnreadableContent("The JSON content could not be parsed.") from exc
    if isinstance(payload, dict) and isinstance(payload.get("records"), list):
        payload = payload["records"]
    if not isinstance(payload, list):
        raise UnreadableContent("JSON content must be an array of records or an object with a 'records' array.")
    if len(payload) > limits.max_rows:
        raise PayloadTooLarge("The JSON has more records than the configured limit.")
    columns: list[str] = []
    seen: set[str] = set()
    rows: list[dict[str, Any]] = []
    for item in payload:
        if not isinstance(item, dict):
            rows.append({"__not_object__": True})
            continue
        if len(item) > limits.max_columns:
            raise PayloadTooLarge("A JSON record has more fields than the configured limit.")
        for key in item:
            if key not in seen:
                seen.add(key)
                columns.append(str(key))
        if any(isinstance(v, str) and len(v) > limits.max_field_chars for v in item.values()):
            rows.append({"__oversized__": True})
            continue
        rows.append(item)
    return ParsedRecords(columns, rows, [])


def parse_records(data: bytes | str, file_format: str, cfg: ExperienceConfig) -> ParsedRecords:
    if file_format not in SUPPORTED_FORMATS:
        raise UnreadableContent("Unsupported format. Use 'csv' or 'json'.")
    text = _decode(data, cfg.limits.max_bytes)
    return _parse_csv(text, cfg) if file_format == "csv" else _parse_json(text, cfg)


# ------------------------------------------------------------------------------------------------ validation
def _is_missing(value: Any) -> bool:
    return value is None or (isinstance(value, str) and not value.strip())


class _Collector:
    def __init__(self, report: ValidationReport, limit: int):
        self.report, self.limit = report, limit
        self.error_rows: set[int] = set()

    def add(
        self, code: str, severity: Severity, message: str, column: str | None = None, row: int | None = None
    ) -> None:
        r = self.report
        r.issue_counts[code] = r.issue_counts.get(code, 0) + 1
        if severity is Severity.ERROR:
            r.error_count += 1
            if row is not None:
                self.error_rows.add(row)
        else:
            r.warning_count += 1
        if len(r.issues) < self.limit:
            r.issues.append(ValidationIssue(code, severity, message, column, row))
        else:
            r.issues_truncated = True


def _number(value: Any) -> float | None:
    if isinstance(value, bool):
        return None
    if isinstance(value, (int, float)):
        return float(value) if math.isfinite(value) else None
    if isinstance(value, str):
        try:
            number = float(value.strip())
        except ValueError:
            return None
        return number if math.isfinite(number) else None
    return None


def validate_records(
    parsed: ParsedRecords,
    schema: DatasetSchema,
    cfg: ExperienceConfig,
    *,
    file_format: str,
    known_customer_ids: Iterable[str] | None = None,
    now: datetime | None = None,
) -> tuple[ValidationReport, list[dict[str, Any]]]:
    """Validate parsed records against ``schema``. Returns the report and the rows that have no ERROR issue."""
    now = now or datetime.now(UTC)
    report = ValidationReport(
        kind=schema.kind.value, file_format=file_format, rows_total=len(parsed.rows), columns_found=list(parsed.columns)
    )
    col = _Collector(report, cfg.limits.max_issues_reported)
    for issue in parsed.file_issues:
        col.add(issue.code, issue.severity, issue.message, issue.column, issue.row)

    spec_names = {c.name for c in schema.columns}
    report.missing_required_columns = [c for c in schema.required_columns if c not in parsed.columns]
    report.unexpected_columns = [c for c in parsed.columns if c not in spec_names]
    for name in report.missing_required_columns:
        col.add("missing_required_column", Severity.ERROR, "A required column is missing.", name)
    for name in report.unexpected_columns:
        col.add(
            "unexpected_column", Severity.WARNING, "A column outside the schema was found and will be ignored.", name
        )
    if report.rows_total == 0:
        col.add("no_records", Severity.ERROR, "The file contains no data rows.")

    id_regex = cfg.customer_id_regex
    known = {str(k) for k in known_customer_ids} if known_customer_ids is not None else None
    earliest = datetime.combine(cfg.min_date, datetime.min.time(), tzinfo=UTC)
    latest = now + timedelta(days=cfg.max_future_days)
    seen_keys: set[tuple[str, ...]] = set()
    missing = {c.name: 0 for c in schema.columns if c.name in parsed.columns}
    last_ts_by_customer: dict[str, datetime] = {}
    ordering_column = schema.timestamp_columns[0] if schema.timestamp_columns else None
    valid_rows: list[dict[str, Any]] = []

    for index, row in enumerate(parsed.rows, start=1):
        before = len(col.error_rows)
        if row.get("__ragged__"):
            col.add(
                "ragged_row", Severity.ERROR, "The row has a different number of fields than the header.", None, index
            )
            continue
        if row.get("__oversized__"):
            col.add("field_too_long", Severity.ERROR, "A field exceeds the configured maximum length.", None, index)
            continue
        if row.get("__not_object__"):
            col.add("record_not_object", Severity.ERROR, "The JSON record is not an object.", None, index)
            continue

        parsed_ts: dict[str, datetime] = {}
        for spec in schema.columns:
            if spec.name not in parsed.columns:
                continue
            value = row.get(spec.name)
            if _is_missing(value):
                missing[spec.name] += 1
                if spec.required:
                    col.add("missing_value", Severity.ERROR, "A required value is missing.", spec.name, index)
                continue
            text = value.strip() if isinstance(value, str) else value

            if spec.name == schema.customer_id_column:
                if not isinstance(text, str) or not id_regex.match(text):
                    report.invalid_customer_ids += 1
                    col.add(
                        "invalid_customer_id",
                        Severity.ERROR,
                        "The customer id has an invalid format.",
                        spec.name,
                        index,
                    )
                elif known is not None and text not in known:
                    report.unknown_customer_ids += 1
                    col.add(
                        "unknown_customer_id",
                        Severity.WARNING,
                        "The customer id is not in the reference customer list.",
                        spec.name,
                        index,
                    )
                continue

            if spec.type in (ColumnType.STRING, ColumnType.TEXT):
                if not isinstance(text, str):
                    col.add("invalid_type", Severity.ERROR, "A text value was expected.", spec.name, index)
                elif spec.type is ColumnType.TEXT and text.startswith(FORMULA_PREFIXES):
                    col.add(
                        "possible_formula",
                        Severity.WARNING,
                        "The text starts with a spreadsheet formula character; escape it before exporting.",
                        spec.name,
                        index,
                    )
            elif spec.type is ColumnType.TIMESTAMP:
                ts = parse_timestamp(text) if isinstance(text, str) else None
                if ts is None:
                    report.invalid_timestamps += 1
                    col.add(
                        "invalid_timestamp",
                        Severity.ERROR,
                        "The value is not an ISO 8601 date or date-time.",
                        spec.name,
                        index,
                    )
                elif ts < earliest:
                    report.invalid_timestamps += 1
                    col.add(
                        "timestamp_too_early",
                        Severity.ERROR,
                        "The timestamp is before the configured minimum date.",
                        spec.name,
                        index,
                    )
                elif ts > latest:
                    report.invalid_timestamps += 1
                    col.add("timestamp_in_future", Severity.ERROR, "The timestamp is in the future.", spec.name, index)
                else:
                    parsed_ts[spec.name] = ts
            elif spec.type in (ColumnType.NUMBER, ColumnType.INTEGER):
                number = _number(text)
                if number is None:
                    col.add("invalid_number", Severity.ERROR, "A finite number was expected.", spec.name, index)
                elif spec.type is ColumnType.INTEGER and number != int(number):
                    col.add("invalid_integer", Severity.ERROR, "A whole number was expected.", spec.name, index)
                elif spec.name == "score" and schema.kind in (DatasetKind.NPS, DatasetKind.CSAT):
                    scale = cfg.surveys.nps if schema.kind is DatasetKind.NPS else cfg.surveys.csat
                    if not scale.scale_min <= number <= scale.scale_max:
                        col.add(
                            "score_out_of_scale",
                            Severity.ERROR,
                            "The score is outside the configured survey scale.",
                            spec.name,
                            index,
                        )
            elif spec.type is ColumnType.CATEGORY:
                if not isinstance(text, str) or text.lower() not in {a.lower() for a in spec.allowed}:
                    col.add(
                        "invalid_category",
                        Severity.ERROR,
                        "The value is not one of the allowed values.",
                        spec.name,
                        index,
                    )
            elif spec.type is ColumnType.JSON_OBJECT:
                obj = text
                if isinstance(text, str):
                    try:
                        obj = json.loads(text, parse_constant=_reject_constant)
                    except (ValueError, RecursionError):
                        obj = None
                if not isinstance(obj, dict):
                    col.add("invalid_json_object", Severity.ERROR, "A JSON object was expected.", spec.name, index)

        _check_cross_field(schema, row, parsed_ts, col, index)

        if schema.duplicate_key and all(k in parsed.columns for k in schema.duplicate_key):
            key = tuple(str(row.get(k, "")).strip() for k in schema.duplicate_key)
            if all(key):
                if key in seen_keys:
                    report.duplicate_records += 1
                    col.add("duplicate_record", Severity.ERROR, "The record duplicates an earlier record.", None, index)
                else:
                    seen_keys.add(key)

        cid = row.get(schema.customer_id_column)
        if ordering_column in parsed_ts and isinstance(cid, str) and cid.strip():
            ts = parsed_ts[ordering_column]
            previous = last_ts_by_customer.get(cid.strip())
            if previous is not None and ts < previous:
                report.out_of_order_records += 1
                col.add(
                    "out_of_order",
                    Severity.WARNING,
                    "The timestamp is earlier than the previous record of the same customer; sequences are re-sorted.",
                    ordering_column,
                    index,
                )
            if previous is None or ts > previous:
                last_ts_by_customer[cid.strip()] = ts

        if len(col.error_rows) == before and not (row.get("__ragged__") or row.get("__oversized__")):
            valid_rows.append(row)

    report.missing_value_counts = missing
    report.rows_valid = len(valid_rows)
    report.valid = report.error_count == 0 and report.rows_total > 0
    return report, valid_rows


def _check_cross_field(
    schema: DatasetSchema, row: Mapping[str, Any], ts: dict[str, datetime], col: _Collector, index: int
) -> None:
    """SLA and ordering relations between timestamp columns (tickets)."""
    if schema.kind is not DatasetKind.TICKETS:
        return
    created, resolved, due = ts.get("created_at"), ts.get("resolved_at"), ts.get("sla_due_at")
    if created and resolved and resolved < created:
        col.add(
            "resolved_before_created", Severity.ERROR, "resolved_at is earlier than created_at.", "resolved_at", index
        )
    if created and due and due < created:
        col.add("sla_before_created", Severity.ERROR, "sla_due_at is earlier than created_at.", "sla_due_at", index)
    status = str(row.get("status", "")).strip().lower()
    if resolved and status in ("open", "in_progress"):
        col.add(
            "resolved_at_with_open_status",
            Severity.WARNING,
            "resolved_at is set although the status is not a resolved status.",
            "resolved_at",
            index,
        )


# ------------------------------------------------------------------------------------------------ entry points
def schema_for(kind: DatasetKind, cfg: ExperienceConfig) -> DatasetSchema:
    return build_schemas(
        severities=cfg.complaints.severities, statuses=cfg.complaints.statuses, sentiment_labels=cfg.sentiment.labels
    )[kind]


def validate_content(
    kind: DatasetKind,
    data: bytes | str,
    file_format: str,
    cfg: ExperienceConfig,
    *,
    known_customer_ids: Iterable[str] | None = None,
    now: datetime | None = None,
) -> tuple[ValidationReport, list[dict[str, Any]]]:
    """Parse + validate. Raises PayloadTooLarge / UnreadableContent for content that cannot be processed at all."""
    parsed = parse_records(data, file_format, cfg)
    return validate_records(
        parsed, schema_for(kind, cfg), cfg, file_format=file_format, known_customer_ids=known_customer_ids, now=now
    )


def load_file(path: Path, cfg: ExperienceConfig) -> tuple[bytes, str]:
    """Read a configured dataset file (size is checked BEFORE reading). Returns (bytes, format)."""
    size = path.stat().st_size
    if size > cfg.limits.max_bytes:
        raise PayloadTooLarge("The dataset file exceeds the configured size limit.")
    return path.read_bytes(), path.suffix.lower().lstrip(".")


# ------------------------------------------------------------------------------------------------ data quality
def quality_summary(report: ValidationReport, rows: list[dict[str, Any]], schema: DatasetSchema) -> dict[str, Any]:
    """Completeness, validity and duplicate rates computed only from the validated file. None when there are no rows."""
    total = report.rows_total
    if total == 0:
        return {
            "rows_total": 0,
            "completeness_pct_by_column": {},
            "valid_row_pct": None,
            "duplicate_pct": None,
            "timestamp_range": None,
        }
    completeness = {name: round(100.0 * (total - n) / total, 2) for name, n in report.missing_value_counts.items()}
    stamps: list[datetime] = []
    for name in schema.timestamp_columns:
        for row in rows:
            ts = parse_timestamp(str(row.get(name, ""))) if not _is_missing(row.get(name)) else None
            if ts:
                stamps.append(ts)
    return {
        "rows_total": total,
        "completeness_pct_by_column": completeness,
        "valid_row_pct": round(100.0 * report.rows_valid / total, 2),
        "duplicate_pct": round(100.0 * report.duplicate_records / total, 2),
        "timestamp_range": (
            {"earliest": min(stamps).isoformat(), "latest": max(stamps).isoformat()} if stamps else None
        ),
    }
