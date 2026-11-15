"""NPS and CSAT calculation from REAL survey responses.

NPS  = % promoters - % detractors            (range -100 to +100)
CSAT = satisfied responses / valid responses * 100

Percentages are computed over VALID responses only (finite number inside the configured scale, inside the optional
survey period). Missing, out-of-scale and out-of-period responses are counted and reported, never silently dropped
or imputed. With zero valid responses the functions raise ``BlockedByMissingData``; they never return 0.
"""

from __future__ import annotations

import math
from collections.abc import Iterable, Mapping
from dataclasses import dataclass
from datetime import datetime
from typing import Any

from trichurn_experience.config import ScaleConfig, SurveyConfig
from trichurn_experience.schemas import BlockedByMissingData
from trichurn_experience.validation import parse_timestamp

NPS_FORMULA = "NPS = (promoters / valid responses) x 100 - (detractors / valid responses) x 100"
CSAT_FORMULA = "CSAT % = (responses with score >= satisfied_min / valid responses) x 100"


class InvalidSurveyPeriod(ValueError):
    """The requested survey period is malformed or reversed."""


@dataclass(frozen=True)
class SurveyPeriod:
    start: datetime | None = None
    end: datetime | None = None  # inclusive

    def contains(self, ts: datetime) -> bool:
        return (self.start is None or ts >= self.start) and (self.end is None or ts <= self.end)


def parse_period(start: str | None, end: str | None) -> SurveyPeriod:
    """Validate ``start``/``end`` (ISO dates or date-times). ``end`` given as a date covers that whole day."""
    s = parse_timestamp(start) if start else None
    e = parse_timestamp(end) if end else None
    if start and s is None:
        raise InvalidSurveyPeriod("period_start is not a valid ISO 8601 date or date-time.")
    if end and e is None:
        raise InvalidSurveyPeriod("period_end is not a valid ISO 8601 date or date-time.")
    if e is not None and end and len(end.strip()) == 10:
        e = e.replace(hour=23, minute=59, second=59, microsecond=999999)
    if s and e and s > e:
        raise InvalidSurveyPeriod("period_start must not be after period_end.")
    return SurveyPeriod(s, e)


def _score(value: Any) -> float | None:
    if value is None or isinstance(value, bool):
        return None
    try:
        v = float(str(value).strip())
    except ValueError:
        return None
    return v if math.isfinite(v) else None


def _filter(
    rows: Iterable[Mapping[str, Any]], scale: ScaleConfig, period: SurveyPeriod
) -> tuple[list[float], dict[str, int]]:
    scores: list[float] = []
    counts = {"responses_total": 0, "missing_score": 0, "out_of_scale": 0, "out_of_period": 0}
    for row in rows:
        counts["responses_total"] += 1
        raw = row.get("score")
        if raw is None or (isinstance(raw, str) and not raw.strip()):
            counts["missing_score"] += 1
            continue
        value = _score(raw)
        if value is None or not scale.scale_min <= value <= scale.scale_max:
            counts["out_of_scale"] += 1
            continue
        if period.start or period.end:
            ts = parse_timestamp(str(row.get("survey_date", "")))
            if ts is None or not period.contains(ts):
                counts["out_of_period"] += 1
                continue
        scores.append(value)
    counts["valid_responses"] = len(scores)
    return scores, counts


def _period_dict(period: SurveyPeriod) -> dict[str, str | None]:
    return {
        "start": period.start.isoformat() if period.start else None,
        "end": period.end.isoformat() if period.end else None,
    }


def compute_nps(
    rows: Iterable[Mapping[str, Any]], scale: ScaleConfig, survey: SurveyConfig, period: SurveyPeriod | None = None
) -> dict[str, Any]:
    period = period or SurveyPeriod()
    scores, counts = _filter(rows, scale, period)
    if not scores:
        raise BlockedByMissingData("nps", "There are no valid NPS responses to calculate from.")
    assert scale.detractor_max is not None and scale.promoter_min is not None
    promoters = sum(s >= scale.promoter_min for s in scores)
    detractors = sum(s <= scale.detractor_max for s in scores)
    passives = len(scores) - promoters - detractors
    n = len(scores)
    p_pct, d_pct = 100.0 * promoters / n, 100.0 * detractors / n
    return {
        "metric": "NPS",
        "formula": NPS_FORMULA,
        "value": round(p_pct - d_pct, 2),
        "promoters": promoters,
        "passives": passives,
        "detractors": detractors,
        "promoters_pct": round(p_pct, 2),
        "passives_pct": round(100.0 * passives / n, 2),
        "detractors_pct": round(d_pct, 2),
        **counts,
        "low_sample": n < survey.min_responses,
        "min_responses": survey.min_responses,
        "scale": {
            "min": scale.scale_min,
            "max": scale.scale_max,
            "detractor_max": scale.detractor_max,
            "promoter_min": scale.promoter_min,
        },
        "period": _period_dict(period),
    }


def compute_csat(
    rows: Iterable[Mapping[str, Any]], scale: ScaleConfig, survey: SurveyConfig, period: SurveyPeriod | None = None
) -> dict[str, Any]:
    period = period or SurveyPeriod()
    scores, counts = _filter(rows, scale, period)
    if not scores:
        raise BlockedByMissingData("csat", "There are no valid CSAT responses to calculate from.")
    assert scale.satisfied_min is not None
    satisfied = sum(s >= scale.satisfied_min for s in scores)
    n = len(scores)
    return {
        "metric": "CSAT",
        "formula": CSAT_FORMULA,
        "value": round(100.0 * satisfied / n, 2),
        "satisfied": satisfied,
        "not_satisfied": n - satisfied,
        **counts,
        "low_sample": n < survey.min_responses,
        "min_responses": survey.min_responses,
        "scale": {"min": scale.scale_min, "max": scale.scale_max, "satisfied_min": scale.satisfied_min},
        "period": _period_dict(period),
    }
