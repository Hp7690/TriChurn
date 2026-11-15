"""Phase 13 experience service.

Independent of the Phase 1-5 adapter and of Phase 9: it reads only ``configs/experience.yaml``, the customer CSV that
already exists in the project and any dataset files explicitly configured under the experience data directory.
Uploaded content is validated in memory and never stored. Nothing is trained, imputed or invented.
"""

from __future__ import annotations

import logging
import threading
from collections import Counter
from collections.abc import Callable, Mapping
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from app.core.errors import ApiError, ErrorCode, internal_error
from trichurn_experience import lifecycle as lifecycle_mod
from trichurn_experience.complaints import aggregate_complaints
from trichurn_experience.config import ExperienceConfig
from trichurn_experience.journey import aggregate_journeys, to_events
from trichurn_experience.requirements import MODULES
from trichurn_experience.schemas import BlockedByMissingData, DatasetKind, ModuleStatus, ValidationReport
from trichurn_experience.sentiment import SentimentModel, sentiment_readiness
from trichurn_experience.surveys import InvalidSurveyPeriod, compute_csat, compute_nps, parse_period
from trichurn_experience.validation import (
    PayloadTooLarge,
    UnreadableContent,
    UnsafePath,
    load_file,
    parse_records,
    quality_summary,
    resolve_safe_path,
    schema_for,
    validate_records,
)

logger = logging.getLogger("trichurn.experience")

MODULE_ORDER = ("lifecycle", "feedback", "sentiment", "complaints", "nps", "csat", "journey")
DATASET_MODULES = {
    "feedback": DatasetKind.FEEDBACK,
    "complaints": DatasetKind.TICKETS,
    "nps": DatasetKind.NPS,
    "csat": DatasetKind.CSAT,
    "journey": DatasetKind.EVENTS,
}


def payload_too_large() -> ApiError:
    return ApiError(ErrorCode.INVALID_INPUT, "The submitted content exceeds the configured size limit.", 413)


class _DatasetState:
    __slots__ = ("kind", "configured", "status", "reason", "report", "rows")

    def __init__(
        self,
        kind: DatasetKind,
        configured: bool,
        status: ModuleStatus,
        reason: str | None = None,
        report: ValidationReport | None = None,
        rows: list[dict[str, Any]] | None = None,
    ):
        self.kind, self.configured, self.status, self.reason = kind, configured, status, reason
        self.report, self.rows = report, rows or []


class ExperienceService:
    def __init__(
        self,
        config: ExperienceConfig | None,
        *,
        project_root: Path,
        customer_csv: Path | None = None,
        config_error: str | None = None,
        probability_provider: Callable[[], Mapping[str, float]] | None = None,
        sentiment_model: SentimentModel | None = None,
        clock: Callable[[], datetime] | None = None,
    ):
        self._cfg = config
        self._config_error = config_error
        self._root = project_root
        self._customer_csv = customer_csv
        self._probabilities = probability_provider
        self._sentiment_model = sentiment_model
        self._clock = clock or (lambda: datetime.now(UTC))
        self._lock = threading.Lock()
        self._cache: dict[str, tuple[tuple[Any, ...], Any]] = {}

    # ------------------------------------------------------------------------------------------ plumbing
    @property
    def config(self) -> ExperienceConfig | None:
        return self._cfg

    def _now(self) -> datetime:
        return self._clock()

    def _stamp(self) -> str:
        return self._now().isoformat()

    def _cached(self, key: str, signature: tuple[Any, ...], build: Callable[[], Any]) -> Any:
        with self._lock:
            hit = self._cache.get(key)
            if hit and hit[0] == signature:
                return hit[1]
        value = build()
        with self._lock:
            self._cache[key] = (signature, value)
        return value

    @staticmethod
    def _signature(path: Path) -> tuple[Any, ...]:
        st = path.stat()
        return (str(path), st.st_mtime_ns, st.st_size)

    def _globally_off(self) -> tuple[ModuleStatus, str] | None:
        if self._cfg is None:
            return ModuleStatus.VALIDATION_FAILED, self._config_error or "The experience configuration is invalid."
        if not self._cfg.enabled:
            return ModuleStatus.DISABLED, "Phase 13 experience intelligence is disabled in configs/experience.yaml."
        return None

    # ------------------------------------------------------------------------------------------ customer table
    def _customer_table(self) -> tuple[list[str], list[dict[str, str]]]:
        assert self._customer_csv is not None
        path = self._customer_csv
        return self._cached("customers", self._signature(path), lambda: lifecycle_mod.read_customer_csv(path))

    def _customer_ids(self) -> set[str] | None:
        if self._customer_csv is None or not self._customer_csv.is_file():
            return None
        columns, rows = self._customer_table()
        if lifecycle_mod.ID_COLUMN not in columns:
            return None
        return {str(r.get(lifecycle_mod.ID_COLUMN, "")).strip() for r in rows}

    # ------------------------------------------------------------------------------------------ configured datasets
    def _dataset_state(self, kind: DatasetKind) -> _DatasetState:
        off = self._globally_off()
        if off:
            return _DatasetState(kind, False, off[0], off[1])
        assert self._cfg is not None
        name = self._cfg.datasets.get(kind.value)
        if not name:
            return _DatasetState(
                kind,
                False,
                ModuleStatus.BLOCKED_BY_MISSING_DATA,
                f"No '{kind.value}' dataset is configured (datasets.{kind.value} is null).",
            )
        try:
            data_dir = (self._root / self._cfg.data_dir).resolve()
            data_dir.relative_to(self._root.resolve())
        except ValueError:
            return _DatasetState(
                kind, True, ModuleStatus.VALIDATION_FAILED, "data_dir must be inside the project directory."
            )
        try:
            path = resolve_safe_path(data_dir, name)
        except UnsafePath as exc:
            return _DatasetState(kind, True, ModuleStatus.VALIDATION_FAILED, str(exc))
        if not path.is_file():
            return _DatasetState(
                kind,
                True,
                ModuleStatus.BLOCKED_BY_MISSING_DATA,
                f"The configured '{kind.value}' dataset file was not found.",
            )
        try:
            signature = self._signature(path)
            return self._cached(f"dataset:{kind.value}", signature, lambda: self._validate_file(kind, path))
        except (PayloadTooLarge, UnreadableContent) as exc:
            return _DatasetState(kind, True, ModuleStatus.VALIDATION_FAILED, str(exc))
        except OSError:
            return _DatasetState(kind, True, ModuleStatus.VALIDATION_FAILED, "The dataset file could not be read.")

    def _validate_file(self, kind: DatasetKind, path: Path) -> _DatasetState:
        assert self._cfg is not None
        data, fmt = load_file(path, self._cfg)
        parsed = parse_records(data, fmt, self._cfg)
        report, rows = validate_records(
            parsed,
            schema_for(kind, self._cfg),
            self._cfg,
            file_format=fmt,
            known_customer_ids=self._customer_ids(),
            now=self._now(),
        )
        if not report.valid:
            return _DatasetState(
                kind,
                True,
                ModuleStatus.VALIDATION_FAILED,
                f"The configured dataset failed validation ({report.error_count} error(s)). "
                "Analytics are not computed on invalid data.",
                report,
            )
        return _DatasetState(kind, True, ModuleStatus.AVAILABLE, None, report, rows)

    # ------------------------------------------------------------------------------------------ lifecycle
    def _lifecycle_shell(self, status: ModuleStatus, reason: str) -> dict[str, Any]:
        thresholds = (
            [
                {"name": g.name, "min_months": g.min_months, "max_months": g.max_months}
                for g in self._cfg.lifecycle.groups
            ]
            if self._cfg
            else []
        )
        return {
            "status": status.value,
            "label": lifecycle_mod.LABEL,
            "is_event_based": False,
            "reason": reason,
            "methodology": lifecycle_mod.METHODOLOGY,
            "thresholds": thresholds,
            "customers_total": 0,
            "customers_analysed": 0,
            "excluded": {"total": 0, "invalid_or_missing_tenure": 0},
            "columns_used": [],
            "columns_missing": [],
            "groups": [],
            "overall": None,
            "risk_distribution": None,
            "assumptions": [],
            "limitations": ["No lifecycle figures are shown without a customer dataset."],
            "source": "none",
            "generated_at": self._stamp(),
        }

    def lifecycle(self) -> dict[str, Any]:
        off = self._globally_off()
        if off:
            return self._lifecycle_shell(*off)
        assert self._cfg is not None
        if not self._cfg.lifecycle.enabled:
            return self._lifecycle_shell(
                ModuleStatus.DISABLED, "The lifecycle module is disabled in configs/experience.yaml."
            )
        if self._customer_csv is None or not self._customer_csv.is_file():
            return self._lifecycle_shell(
                ModuleStatus.BLOCKED_BY_MISSING_DATA,
                "The customer dataset file was not found, so lifecycle groups cannot be computed.",
            )
        try:
            columns, rows = self._customer_table()
        except (OSError, ValueError, UnicodeDecodeError):
            return self._lifecycle_shell(ModuleStatus.VALIDATION_FAILED, "The customer dataset could not be read.")
        probabilities: Mapping[str, float] | None = None
        if self._probabilities is not None:
            try:
                probabilities = self._probabilities()
            except Exception as exc:  # noqa: BLE001 - provider is external code; degrade, never break the API
                logger.warning("Probability provider failed (%s); risk distribution withheld.", type(exc).__name__)
        result = lifecycle_mod.compute_lifecycle(
            columns, rows, self._cfg.lifecycle, probability_by_customer=probabilities
        )
        result["source"] = f"Customer dataset: {self._customer_csv.name}"
        result["generated_at"] = self._stamp()
        return result

    # ------------------------------------------------------------------------------------------ module status
    def _requirements(self, name: str) -> dict[str, Any]:
        meta = MODULES[name]
        kind = meta["dataset_kind"]
        required: list[str] = []
        optional: list[str] = []
        if kind and self._cfg is not None:
            schema = schema_for(DatasetKind(kind), self._cfg)
            required, optional = list(schema.required_columns), list(schema.optional_columns)
        elif name == "lifecycle":
            required, optional = list(lifecycle_mod.REQUIRED_COLUMNS), list(lifecycle_mod.OPTIONAL_COLUMNS)
        return {
            "needs": list(meta["needs"]),
            "note": meta["note"],
            "dataset_kind": kind,
            "required_columns": required,
            "optional_columns": optional,
        }

    @staticmethod
    def _validation_summary(report: ValidationReport | None) -> dict[str, Any] | None:
        if report is None:
            return None
        return {
            "rows_total": report.rows_total,
            "rows_valid": report.rows_valid,
            "error_count": report.error_count,
            "warning_count": report.warning_count,
            "valid": report.valid,
        }

    def _envelope(
        self,
        name: str,
        status: ModuleStatus,
        reason: str | None,
        state: _DatasetState | None,
        metrics: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        return {
            "module": name,
            "title": MODULES[name]["title"],
            "status": status.value,
            "reason": reason,
            "dataset_configured": bool(state and state.configured),
            "requirements": self._requirements(name),
            "validation": self._validation_summary(state.report if state else None),
            "metrics": metrics,
            "generated_at": self._stamp(),
        }

    def module_status(
        self, name: str, *, period_start: str | None = None, period_end: str | None = None
    ) -> dict[str, Any]:
        if name not in MODULES:
            raise ApiError(ErrorCode.NOT_FOUND, "Resource not found.", 404)
        try:
            return self._module_status(name, period_start, period_end)
        except ApiError:
            raise
        except Exception as exc:  # noqa: BLE001
            raise internal_error(exc) from exc

    def _module_status(self, name: str, period_start: str | None, period_end: str | None) -> dict[str, Any]:
        if name == "lifecycle":
            lc = self.lifecycle()
            return self._envelope(
                name,
                ModuleStatus(lc["status"]),
                lc["reason"],
                None,
                {
                    "customers_analysed": lc["customers_analysed"],
                    "groups": len(lc["groups"]),
                    "label": lc["label"],
                    "is_event_based": False,
                }
                if lc["customers_analysed"]
                else None,
            )

        if name == "sentiment":
            fb = self._dataset_state(DatasetKind.FEEDBACK)
            if fb.status is ModuleStatus.AVAILABLE:
                labelled = sum(1 for r in fb.rows if str(r.get("sentiment_label") or "").strip())
                assert self._cfg is not None
                status, reason = sentiment_readiness(
                    feedback_valid_records=len(fb.rows),
                    labelled_records=labelled,
                    cfg=self._cfg.sentiment,
                    model=self._sentiment_model,
                )
                meta = self._sentiment_model.metadata if self._sentiment_model else None
                metrics: dict[str, Any] = {"labelled_records": labelled, "model_registered": meta is not None}
                if meta is not None:
                    metrics["model"] = {
                        "name": meta.name,
                        "version": meta.version,
                        "trained_at": meta.trained_at,
                        "labels": list(meta.labels),
                        "evaluation": meta.evaluation.to_dict() if meta.evaluation else None,
                    }
                return self._envelope(name, status, reason, fb, metrics)
            if fb.status is ModuleStatus.BLOCKED_BY_MISSING_DATA and self._cfg is not None:
                _, reason = sentiment_readiness(
                    feedback_valid_records=0, labelled_records=0, cfg=self._cfg.sentiment, model=self._sentiment_model
                )
                return self._envelope(name, ModuleStatus.BLOCKED_BY_MISSING_DATA, reason, fb)
            return self._envelope(name, fb.status, fb.reason, fb)

        state = self._dataset_state(DATASET_MODULES[name])
        if state.status is not ModuleStatus.AVAILABLE:
            return self._envelope(name, state.status, state.reason, state)
        assert self._cfg is not None
        try:
            if name == "feedback":
                labels = Counter(
                    str(r.get("sentiment_label") or "").strip().lower()
                    for r in state.rows
                    if str(r.get("sentiment_label") or "").strip()
                )
                metrics = {
                    "records": len(state.rows),
                    "labelled_records": sum(labels.values()),
                    "human_label_counts": dict(labels),
                }
            elif name == "complaints":
                metrics = aggregate_complaints(state.rows, self._cfg.complaints, now=self._now())
            elif name in ("nps", "csat"):
                period = parse_period(period_start, period_end)
                metrics = (
                    compute_nps(state.rows, self._cfg.surveys.nps, self._cfg.surveys, period)
                    if name == "nps"
                    else compute_csat(state.rows, self._cfg.surveys.csat, self._cfg.surveys, period)
                )
            else:
                metrics = aggregate_journeys(to_events(state.rows), min_events=self._cfg.journey_min_events)
        except InvalidSurveyPeriod as exc:
            raise ApiError(ErrorCode.INVALID_INPUT, str(exc), 422) from exc
        except BlockedByMissingData as exc:
            return self._envelope(name, ModuleStatus.BLOCKED_BY_MISSING_DATA, exc.reason, state)
        return self._envelope(name, ModuleStatus.AVAILABLE, None, state, metrics)

    # ------------------------------------------------------------------------------------------ availability
    def availability(self) -> dict[str, Any]:
        off = self._globally_off()
        modules = [self.module_status(n) for n in MODULE_ORDER]
        summary = {s.value: 0 for s in ModuleStatus}
        for m in modules:
            summary[m["status"]] += 1
        lc = self.lifecycle()
        lifecycle_summary = None
        if lc["customers_analysed"]:
            lifecycle_summary = {
                "label": lc["label"],
                "is_event_based": False,
                "customers_analysed": lc["customers_analysed"],
                "groups": [
                    {"name": g["name"], "customers": g["customers"], "share_pct": g["share_pct"]} for g in lc["groups"]
                ],
            }
        datasets: dict[str, dict[str, Any] | None] = {}
        for kind in DatasetKind:
            st = self._dataset_state(kind)
            datasets[kind.value] = self._validation_summary(st.report)
        return {
            "enabled": bool(self._cfg and self._cfg.enabled),
            "config_error": off[1] if off and off[0] is ModuleStatus.VALIDATION_FAILED else None,
            "summary": summary,
            "modules": modules,
            "lifecycle_summary": lifecycle_summary,
            "data_quality": {"datasets": datasets, "customer_dataset": self._customer_quality()},
            "notices": [
                "Modules marked BLOCKED_BY_MISSING_DATA need the real datasets listed under each module.",
                "Nothing is inferred from churn probability, TechSupport or any other Telco column.",
                "The lifecycle view is a tenure-based proxy, not an event-based customer journey.",
            ],
            "generated_at": self._stamp(),
        }

    def _customer_quality(self) -> dict[str, Any] | None:
        if self._globally_off() or self._customer_csv is None or not self._customer_csv.is_file():
            return None
        try:
            columns, rows = self._customer_table()
        except (OSError, ValueError, UnicodeDecodeError):
            return None
        ids = (
            [str(r.get(lifecycle_mod.ID_COLUMN, "")).strip() for r in rows]
            if lifecycle_mod.ID_COLUMN in columns
            else []
        )
        dup = sum(n - 1 for n in Counter(ids).values() if n > 1) if ids else None

        def missing(col: str) -> int | None:
            return sum(1 for r in rows if not str(r.get(col, "")).strip()) if col in columns else None

        bad_tenure = None
        if "tenure" in columns:
            values = [lifecycle_mod.to_float(r.get("tenure")) for r in rows]
            bad_tenure = sum(1 for v in values if v is None or v < 0)
        return {
            "source": self._customer_csv.name,
            "rows": len(rows),
            "columns": len(columns),
            "duplicate_customer_ids": dup,
            "missing_tenure_or_invalid": bad_tenure,
            "missing_total_charges": missing("TotalCharges"),
            "missing_monthly_charges": missing("MonthlyCharges"),
            "missing_churn_label": missing("Churn"),
        }

    # ------------------------------------------------------------------------------------------ validation of uploads
    def _checked_report(
        self, kind: DatasetKind, fmt: str, content: str
    ) -> tuple[ValidationReport, list[dict[str, Any]]]:
        off = self._globally_off()
        if off:
            raise ApiError(ErrorCode.CAPABILITY_UNAVAILABLE, off[1], 503)
        assert self._cfg is not None
        try:
            parsed = parse_records(content, fmt, self._cfg)
            return validate_records(
                parsed,
                schema_for(kind, self._cfg),
                self._cfg,
                file_format=fmt,
                known_customer_ids=self._customer_ids(),
                now=self._now(),
            )
        except PayloadTooLarge as exc:
            raise payload_too_large() from exc
        except UnreadableContent as exc:
            raise ApiError(ErrorCode.INVALID_INPUT, str(exc), 422) from exc

    def validate(self, kind: DatasetKind, fmt: str, content: str) -> dict[str, Any]:
        try:
            report, _ = self._checked_report(kind, fmt, content)
        except ApiError:
            raise
        except Exception as exc:  # noqa: BLE001
            raise internal_error(exc) from exc
        return {"report": report.to_dict(), "generated_at": self._stamp()}

    def data_quality(self, kind: DatasetKind, fmt: str, content: str) -> dict[str, Any]:
        try:
            report, rows = self._checked_report(kind, fmt, content)
            assert self._cfg is not None
            return {
                "report": report.to_dict(),
                "quality": quality_summary(report, rows, schema_for(kind, self._cfg)),
                "generated_at": self._stamp(),
            }
        except ApiError:
            raise
        except Exception as exc:  # noqa: BLE001
            raise internal_error(exc) from exc

    def max_body_bytes(self) -> int:
        """Pre-parse request-size ceiling (JSON escaping can inflate content, so allow 2x plus a small envelope)."""
        return (self._cfg.limits.max_bytes if self._cfg else 5 * 1024 * 1024) * 2 + 4096
