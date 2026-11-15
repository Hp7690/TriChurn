"""Typed, strictly validated loader for ``configs/experience.yaml``.

Unknown keys, wrong types, non-contiguous lifecycle groups and inconsistent survey scales are rejected with a
``ExperienceConfigError``. Error messages name the key, never echo a file path or a value from outside the config.
"""

from __future__ import annotations

import re
from collections.abc import Mapping
from dataclasses import dataclass, field
from datetime import date
from pathlib import Path
from typing import Any

import yaml

from trichurn_experience.schemas import DatasetKind


class ExperienceConfigError(ValueError):
    """The experience configuration is malformed."""


# ------------------------------------------------------------------------------------------------ helpers
def _only_keys(section: str, data: Mapping[str, Any], allowed: set[str]) -> None:
    unknown = set(data) - allowed
    if unknown:
        raise ExperienceConfigError(f"{section}: unknown key(s) {sorted(unknown)}.")


def _mapping(section: str, value: Any) -> Mapping[str, Any]:
    if value is None:
        return {}
    if not isinstance(value, Mapping):
        raise ExperienceConfigError(f"{section} must be a mapping.")
    return value


def _int(section: str, value: Any, *, minimum: int | None = None) -> int:
    if isinstance(value, bool) or not isinstance(value, int):
        raise ExperienceConfigError(f"{section} must be an integer.")
    if minimum is not None and value < minimum:
        raise ExperienceConfigError(f"{section} must be >= {minimum}.")
    return value


def _num(section: str, value: Any) -> float:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise ExperienceConfigError(f"{section} must be a number.")
    return float(value)


def _str_list(section: str, value: Any, *, minimum: int = 1) -> tuple[str, ...]:
    if not isinstance(value, list) or not all(isinstance(v, str) and v.strip() for v in value):
        raise ExperienceConfigError(f"{section} must be a list of non-empty strings.")
    if len(value) < minimum or len(set(value)) != len(value):
        raise ExperienceConfigError(f"{section} must have >= {minimum} unique entries.")
    return tuple(value)


# ------------------------------------------------------------------------------------------------ sections
@dataclass(frozen=True)
class Limits:
    max_bytes: int = 5 * 1024 * 1024
    max_rows: int = 100_000
    max_columns: int = 50
    max_field_chars: int = 10_000
    max_issues_reported: int = 200


@dataclass(frozen=True)
class LifecycleGroup:
    name: str
    min_months: int
    max_months: int | None  # exclusive; None = open-ended


@dataclass(frozen=True)
class LifecycleConfig:
    enabled: bool = True
    min_group_size_for_rate: int = 30
    probability_field: str | None = "churn_probability"
    risk_low_max: float = 0.20
    risk_medium_max: float = 0.50
    groups: tuple[LifecycleGroup, ...] = (
        LifecycleGroup("New Customer", 0, 6),
        LifecycleGroup("Early Lifecycle", 6, 12),
        LifecycleGroup("Developing Customer", 12, 24),
        LifecycleGroup("Established Customer", 24, 48),
        LifecycleGroup("Long-Term Customer", 48, None),
    )


@dataclass(frozen=True)
class ScaleConfig:
    scale_min: float
    scale_max: float
    # NPS uses detractor_max / promoter_min; CSAT uses satisfied_min. Unused fields stay None.
    detractor_max: float | None = None
    promoter_min: float | None = None
    satisfied_min: float | None = None


@dataclass(frozen=True)
class SurveyConfig:
    min_responses: int = 30
    nps: ScaleConfig = ScaleConfig(0, 10, detractor_max=6, promoter_min=9)
    csat: ScaleConfig = ScaleConfig(1, 5, satisfied_min=4)


@dataclass(frozen=True)
class ComplaintConfig:
    severities: tuple[str, ...] = ("low", "medium", "high", "critical")
    statuses: tuple[str, ...] = ("open", "in_progress", "resolved", "closed")
    resolved_statuses: tuple[str, ...] = ("resolved", "closed")
    min_records: int = 30


@dataclass(frozen=True)
class SentimentConfig:
    labels: tuple[str, ...] = ("positive", "neutral", "negative")
    min_labelled_records: int = 200


@dataclass(frozen=True)
class ExperienceConfig:
    enabled: bool = True
    limits: Limits = field(default_factory=Limits)
    customer_id_pattern: str = r"^[A-Za-z0-9][A-Za-z0-9_-]{0,63}$"
    min_date: date = date(1990, 1, 1)
    max_future_days: int = 1
    data_dir: str = "data/experience"
    datasets: Mapping[str, str | None] = field(default_factory=lambda: {k.value: None for k in DatasetKind})
    lifecycle: LifecycleConfig = field(default_factory=LifecycleConfig)
    surveys: SurveyConfig = field(default_factory=SurveyConfig)
    complaints: ComplaintConfig = field(default_factory=ComplaintConfig)
    journey_min_events: int = 30
    sentiment: SentimentConfig = field(default_factory=SentimentConfig)

    @property
    def customer_id_regex(self) -> re.Pattern[str]:
        return re.compile(self.customer_id_pattern)


# ------------------------------------------------------------------------------------------------ parsing
def _parse_limits(raw: Any) -> Limits:
    d = _mapping("limits", raw)
    _only_keys("limits", d, {"max_bytes", "max_rows", "max_columns", "max_field_chars", "max_issues_reported"})
    base = Limits()
    return Limits(
        *(
            _int(f"limits.{k}", d.get(k, getattr(base, k)), minimum=1)
            for k in ("max_bytes", "max_rows", "max_columns", "max_field_chars", "max_issues_reported")
        )
    )


def _parse_lifecycle(raw: Any) -> LifecycleConfig:
    d = _mapping("lifecycle", raw)
    _only_keys("lifecycle", d, {"enabled", "min_group_size_for_rate", "probability_field", "risk_bands", "groups"})
    base = LifecycleConfig()
    enabled = d.get("enabled", True)
    if not isinstance(enabled, bool):
        raise ExperienceConfigError("lifecycle.enabled must be true or false.")
    prob = d.get("probability_field", base.probability_field)
    if prob is not None and not (isinstance(prob, str) and prob.strip()):
        raise ExperienceConfigError("lifecycle.probability_field must be a column name or null.")
    bands = _mapping("lifecycle.risk_bands", d.get("risk_bands"))
    _only_keys("lifecycle.risk_bands", bands, {"low_max", "medium_max"})
    low, med = (
        _num("lifecycle.risk_bands.low_max", bands.get("low_max", base.risk_low_max)),
        _num("lifecycle.risk_bands.medium_max", bands.get("medium_max", base.risk_medium_max)),
    )
    if not 0 < low < med <= 1:
        raise ExperienceConfigError("lifecycle.risk_bands must satisfy 0 < low_max < medium_max <= 1.")
    groups_raw = d.get("groups")
    groups = base.groups
    if groups_raw is not None:
        if not isinstance(groups_raw, list) or len(groups_raw) < 2:
            raise ExperienceConfigError("lifecycle.groups must be a list of at least 2 groups.")
        parsed: list[LifecycleGroup] = []
        for i, g in enumerate(groups_raw):
            g = _mapping(f"lifecycle.groups[{i}]", g)
            _only_keys(f"lifecycle.groups[{i}]", g, {"name", "min_months", "max_months"})
            name = g.get("name")
            if not isinstance(name, str) or not name.strip():
                raise ExperienceConfigError(f"lifecycle.groups[{i}].name must be a non-empty string.")
            mx = g.get("max_months")
            parsed.append(
                LifecycleGroup(
                    name.strip(),
                    _int(f"lifecycle.groups[{i}].min_months", g.get("min_months"), minimum=0),
                    None if mx is None else _int(f"lifecycle.groups[{i}].max_months", mx, minimum=1),
                )
            )
        _check_groups(parsed)
        groups = tuple(parsed)
    return LifecycleConfig(
        enabled,
        _int(
            "lifecycle.min_group_size_for_rate",
            d.get("min_group_size_for_rate", base.min_group_size_for_rate),
            minimum=1,
        ),
        prob,
        low,
        med,
        groups,
    )


def _check_groups(groups: list[LifecycleGroup]) -> None:
    if len({g.name for g in groups}) != len(groups):
        raise ExperienceConfigError("lifecycle.groups names must be unique.")
    if groups[0].min_months != 0:
        raise ExperienceConfigError("The first lifecycle group must start at 0 months.")
    for prev, nxt in zip(groups, groups[1:], strict=False):
        if prev.max_months is None:
            raise ExperienceConfigError("Only the last lifecycle group may be open-ended.")
        if prev.max_months <= prev.min_months:
            raise ExperienceConfigError(f"Lifecycle group '{prev.name}' must have max_months > min_months.")
        if nxt.min_months != prev.max_months:
            raise ExperienceConfigError("Lifecycle groups must be contiguous (next min_months == previous max_months).")
    if groups[-1].max_months is not None:
        raise ExperienceConfigError("The last lifecycle group must be open-ended (max_months: null).")


def _scale(section: str, raw: Any, default: ScaleConfig, *, nps: bool) -> ScaleConfig:
    d = _mapping(section, raw)
    keys = {"scale_min", "scale_max"} | ({"detractor_max", "promoter_min"} if nps else {"satisfied_min"})
    _only_keys(section, d, keys)
    lo, hi = (
        _num(f"{section}.scale_min", d.get("scale_min", default.scale_min)),
        _num(f"{section}.scale_max", d.get("scale_max", default.scale_max)),
    )
    if not lo < hi:
        raise ExperienceConfigError(f"{section}.scale_min must be < scale_max.")
    if nps:
        det = _num(f"{section}.detractor_max", d.get("detractor_max", default.detractor_max))
        pro = _num(f"{section}.promoter_min", d.get("promoter_min", default.promoter_min))
        if not lo <= det < pro <= hi:
            raise ExperienceConfigError(
                f"{section} must satisfy scale_min <= detractor_max < promoter_min <= scale_max."
            )
        return ScaleConfig(lo, hi, detractor_max=det, promoter_min=pro)
    sat = _num(f"{section}.satisfied_min", d.get("satisfied_min", default.satisfied_min))
    if not lo < sat <= hi:
        raise ExperienceConfigError(f"{section}.satisfied_min must be in (scale_min, scale_max].")
    return ScaleConfig(lo, hi, satisfied_min=sat)


def parse_config(raw: Mapping[str, Any] | None) -> ExperienceConfig:
    d = _mapping("experience config", raw)
    _only_keys(
        "experience config",
        d,
        {
            "enabled",
            "limits",
            "customer_id",
            "timestamps",
            "data_dir",
            "datasets",
            "lifecycle",
            "surveys",
            "complaints",
            "journey",
            "sentiment",
        },
    )
    enabled = d.get("enabled", True)
    if not isinstance(enabled, bool):
        raise ExperienceConfigError("enabled must be true or false.")

    cid = _mapping("customer_id", d.get("customer_id"))
    _only_keys("customer_id", cid, {"pattern"})
    pattern = cid.get("pattern", ExperienceConfig().customer_id_pattern)
    if not isinstance(pattern, str):
        raise ExperienceConfigError("customer_id.pattern must be a string.")
    try:
        re.compile(pattern)
    except re.error as exc:
        raise ExperienceConfigError("customer_id.pattern is not a valid regular expression.") from exc

    ts = _mapping("timestamps", d.get("timestamps"))
    _only_keys("timestamps", ts, {"min_date", "max_future_days"})
    raw_min = ts.get("min_date", "1990-01-01")
    try:
        min_date = raw_min if isinstance(raw_min, date) else date.fromisoformat(str(raw_min))
    except ValueError as exc:
        raise ExperienceConfigError("timestamps.min_date must be an ISO date (YYYY-MM-DD).") from exc

    data_dir = d.get("data_dir", "data/experience")
    if not isinstance(data_dir, str) or not data_dir.strip():
        raise ExperienceConfigError("data_dir must be a non-empty relative path.")

    ds_raw = _mapping("datasets", d.get("datasets"))
    _only_keys("datasets", ds_raw, {k.value for k in DatasetKind})
    datasets: dict[str, str | None] = {k.value: None for k in DatasetKind}
    for key, value in ds_raw.items():
        if value is not None and not (isinstance(value, str) and value.strip()):
            raise ExperienceConfigError(f"datasets.{key} must be a relative file name or null.")
        datasets[key] = value

    surveys = _mapping("surveys", d.get("surveys"))
    _only_keys("surveys", surveys, {"min_responses", "nps", "csat"})
    sbase = SurveyConfig()
    survey_cfg = SurveyConfig(
        _int("surveys.min_responses", surveys.get("min_responses", sbase.min_responses), minimum=1),
        _scale("surveys.nps", surveys.get("nps"), sbase.nps, nps=True),
        _scale("surveys.csat", surveys.get("csat"), sbase.csat, nps=False),
    )

    comp = _mapping("complaints", d.get("complaints"))
    _only_keys("complaints", comp, {"severities", "statuses", "resolved_statuses", "min_records"})
    cbase = ComplaintConfig()
    statuses = _str_list("complaints.statuses", comp.get("statuses", list(cbase.statuses)))
    resolved = _str_list("complaints.resolved_statuses", comp.get("resolved_statuses", list(cbase.resolved_statuses)))
    if not set(resolved) <= set(statuses):
        raise ExperienceConfigError("complaints.resolved_statuses must be a subset of complaints.statuses.")
    complaint_cfg = ComplaintConfig(
        _str_list("complaints.severities", comp.get("severities", list(cbase.severities))),
        statuses,
        resolved,
        _int("complaints.min_records", comp.get("min_records", cbase.min_records), minimum=1),
    )

    journey = _mapping("journey", d.get("journey"))
    _only_keys("journey", journey, {"min_events"})

    sent = _mapping("sentiment", d.get("sentiment"))
    _only_keys("sentiment", sent, {"labels", "min_labelled_records"})
    sbase2 = SentimentConfig()
    sentiment_cfg = SentimentConfig(
        _str_list("sentiment.labels", sent.get("labels", list(sbase2.labels)), minimum=2),
        _int(
            "sentiment.min_labelled_records", sent.get("min_labelled_records", sbase2.min_labelled_records), minimum=1
        ),
    )

    return ExperienceConfig(
        enabled=enabled,
        limits=_parse_limits(d.get("limits")),
        customer_id_pattern=pattern,
        min_date=min_date,
        max_future_days=_int("timestamps.max_future_days", ts.get("max_future_days", 1), minimum=0),
        data_dir=data_dir,
        datasets=datasets,
        lifecycle=_parse_lifecycle(d.get("lifecycle")),
        surveys=survey_cfg,
        complaints=complaint_cfg,
        journey_min_events=_int("journey.min_events", journey.get("min_events", 30), minimum=1),
        sentiment=sentiment_cfg,
    )


def load_experience_config(path: str | Path) -> ExperienceConfig:
    """Load and validate a YAML file. A missing file is an error (callers decide how to degrade)."""
    p = Path(path)
    try:
        with open(p, encoding="utf-8") as fh:
            raw = yaml.safe_load(fh)  # safe_load: no object construction from the file
    except FileNotFoundError as exc:
        raise ExperienceConfigError("Experience configuration file not found.") from exc
    except yaml.YAMLError as exc:
        raise ExperienceConfigError("Experience configuration is not valid YAML.") from exc
    return parse_config(raw)
