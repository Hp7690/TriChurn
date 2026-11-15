"""Tenure-based customer lifecycle PROXY.

This groups customers by how long they have been customers (``tenure`` in months). It is NOT an event-based customer
journey: it knows nothing about what a customer did, only how long they have stayed. Everything is computed from the
columns present in the dataset; nothing is imputed or invented.

Input rows are plain dicts (as read by ``csv.DictReader``). Pure standard library.
"""

from __future__ import annotations

import csv
import math
import statistics
from collections import Counter
from collections.abc import Callable, Iterable, Mapping
from pathlib import Path
from typing import Any

from trichurn_experience.config import LifecycleConfig, LifecycleGroup
from trichurn_experience.schemas import ModuleStatus

REQUIRED_COLUMNS = ("tenure",)
OPTIONAL_COLUMNS = ("Contract", "MonthlyCharges", "TotalCharges", "Churn")
ID_COLUMN = "customerID"
LABEL = "TENURE_PROXY"
RISK_BANDS = ("LOW", "MEDIUM", "HIGH")

METHODOLOGY = (
    "Customers are grouped by tenure (months as a customer) using the configured thresholds: each group includes its "
    "minimum and excludes its maximum, and the last group is open-ended. This is a tenure-based lifecycle proxy, not "
    "an event-based customer journey. Churn figures are the observed Churn labels in the dataset (actual), not model "
    "predictions. Churn percentages are withheld for groups smaller than the configured minimum group size."
)


def read_customer_csv(path: Path, *, max_bytes: int = 50 * 1024 * 1024) -> tuple[list[str], list[dict[str, str]]]:
    """Read a customer CSV (e.g. the Telco dataset) as strings. Size is checked before reading."""
    if path.stat().st_size > max_bytes:
        raise ValueError("The customer dataset exceeds the size limit.")
    with open(path, encoding="utf-8-sig", newline="") as fh:
        reader = csv.DictReader(fh)
        columns = list(reader.fieldnames or [])
        return columns, [dict(r) for r in reader]


def to_float(value: Any) -> float | None:
    """Finite float or None (blank, non-numeric, NaN and infinity are all None)."""
    if value is None or isinstance(value, bool):
        return None
    try:
        number = float(str(value).strip())
    except ValueError:
        return None
    return number if math.isfinite(number) else None


def assign_group(tenure_months: float, groups: Iterable[LifecycleGroup]) -> str | None:
    """Group name for a tenure value, or None when it is negative/non-finite (invalid)."""
    if not math.isfinite(tenure_months) or tenure_months < 0:
        return None
    for g in groups:
        if tenure_months >= g.min_months and (g.max_months is None or tenure_months < g.max_months):
            return g.name
    return None


def _summary(values: list[float]) -> dict[str, float | int | None]:
    if not values:
        return {"count": 0, "mean": None, "median": None, "min": None, "max": None, "sum": None}
    return {
        "count": len(values),
        "mean": round(statistics.fmean(values), 2),
        "median": round(statistics.median(values), 2),
        "min": round(min(values), 2),
        "max": round(max(values), 2),
        "sum": round(math.fsum(values), 2),
    }


def risk_band(probability: float, cfg: LifecycleConfig) -> str:
    return "LOW" if probability < cfg.risk_low_max else "MEDIUM" if probability < cfg.risk_medium_max else "HIGH"


def compute_lifecycle(
    columns: list[str],
    rows: list[Mapping[str, Any]],
    cfg: LifecycleConfig,
    *,
    probability_by_customer: Mapping[str, float] | None = None,
) -> dict[str, Any]:
    """Aggregate customers into tenure lifecycle groups.

    ``probability_by_customer`` (optional) maps customerID -> existing churn probability; when absent and the dataset
    has no ``cfg.probability_field`` column, the risk distribution is reported as BLOCKED_BY_MISSING_DATA.
    """
    missing_required = [c for c in REQUIRED_COLUMNS if c not in columns]
    if missing_required:
        return {
            "status": ModuleStatus.VALIDATION_FAILED.value,
            "label": LABEL,
            "is_event_based": False,
            "reason": f"Required column(s) missing from the customer dataset: {', '.join(missing_required)}.",
            "methodology": METHODOLOGY,
            "groups": [],
            "thresholds": _thresholds(cfg),
            "customers_total": len(rows),
            "customers_analysed": 0,
            "excluded": {"total": len(rows), "invalid_or_missing_tenure": len(rows)},
            "columns_used": [],
            "columns_missing": missing_required,
            "overall": None,
            "risk_distribution": None,
            "assumptions": _assumptions(cfg),
            "limitations": _limitations(),
        }

    has = {c: c in columns for c in OPTIONAL_COLUMNS}
    prob_field = cfg.probability_field if cfg.probability_field and cfg.probability_field in columns else None
    use_probabilities = prob_field is not None or probability_by_customer is not None

    buckets: dict[str, list[Mapping[str, Any]]] = {g.name: [] for g in cfg.groups}
    excluded_tenure = 0
    for row in rows:
        tenure = to_float(row.get("tenure"))
        name = assign_group(tenure, cfg.groups) if tenure is not None else None
        if name is None:
            excluded_tenure += 1
            continue
        buckets[name].append(row)

    analysed = sum(len(v) for v in buckets.values())
    groups_out: list[dict[str, Any]] = []
    total_churned = total_known_churn = 0
    risk_total: Counter[str] = Counter()
    risk_missing_total = 0

    for g in cfg.groups:
        members = buckets[g.name]
        n = len(members)
        churn_known = churned = 0
        if has["Churn"]:
            for r in members:
                label = str(r.get("Churn", "")).strip().lower()
                if label in ("yes", "no"):
                    churn_known += 1
                    churned += label == "yes"
        total_churned += churned
        total_known_churn += churn_known
        sufficient = n >= cfg.min_group_size_for_rate and churn_known >= cfg.min_group_size_for_rate

        contract: dict[str, int] = {}
        if has["Contract"]:
            contract = dict(sorted(Counter((str(r.get("Contract", "")).strip() or "Unknown") for r in members).items()))
        monthly = (
            [v for v in (to_float(r.get("MonthlyCharges")) for r in members) if v is not None]
            if has["MonthlyCharges"]
            else []
        )
        total_charges_missing = 0
        totals: list[float] = []
        if has["TotalCharges"]:
            for r in members:
                v = to_float(r.get("TotalCharges"))
                if v is None:
                    total_charges_missing += 1
                else:
                    totals.append(v)

        risk: dict[str, Any] | None = None
        if use_probabilities:
            counts: Counter[str] = Counter()
            missing_prob = 0
            for r in members:
                p = to_float(r.get(prob_field)) if prob_field else None
                if p is None and probability_by_customer is not None:
                    p = to_float(probability_by_customer.get(str(r.get(ID_COLUMN, ""))))
                if p is None or not 0 <= p <= 1:
                    missing_prob += 1
                else:
                    counts[risk_band(p, cfg)] += 1
            risk = {"counts": {b: counts.get(b, 0) for b in RISK_BANDS}, "missing_probability": missing_prob}
            risk_total.update(counts)
            risk_missing_total += missing_prob

        groups_out.append(
            {
                "name": g.name,
                "min_months": g.min_months,
                "max_months": g.max_months,
                "customers": n,
                "share_pct": round(100.0 * n / analysed, 2) if analysed else None,
                "churn": (
                    {
                        "known_labels": churn_known,
                        "churned": churned,
                        "churn_rate_pct": round(100.0 * churned / churn_known, 2) if sufficient else None,
                        "rate_withheld_reason": None
                        if sufficient
                        else f"Fewer than {cfg.min_group_size_for_rate} labelled customers in this group.",
                    }
                    if has["Churn"]
                    else None
                ),
                "contract_distribution": contract if has["Contract"] else None,
                "monthly_charges": _summary(monthly) if has["MonthlyCharges"] else None,
                "total_charges": (
                    {**_summary(totals), "missing": total_charges_missing} if has["TotalCharges"] else None
                ),
                "risk": risk,
            }
        )

    overall_rate = round(100.0 * total_churned / total_known_churn, 2) if total_known_churn else None
    return {
        "status": (
            ModuleStatus.AVAILABLE
            if analysed and has["Churn"]
            else ModuleStatus.PARTIALLY_AVAILABLE
            if analysed
            else ModuleStatus.BLOCKED_BY_MISSING_DATA
        ).value,
        "label": LABEL,
        "is_event_based": False,
        "reason": (
            None
            if analysed and has["Churn"]
            else "The dataset has no Churn column, so churn distribution is unavailable."
            if analysed
            else "No customer rows with a valid tenure were found."
        ),
        "methodology": METHODOLOGY,
        "thresholds": _thresholds(cfg),
        "customers_total": len(rows),
        "customers_analysed": analysed,
        "excluded": {"total": excluded_tenure, "invalid_or_missing_tenure": excluded_tenure},
        "columns_used": [c for c in (*REQUIRED_COLUMNS, *OPTIONAL_COLUMNS) if c in columns],
        "columns_missing": [c for c in OPTIONAL_COLUMNS if c not in columns],
        "groups": groups_out,
        "overall": {"churn_labels_known": total_known_churn, "churned": total_churned, "churn_rate_pct": overall_rate},
        "risk_distribution": (
            {
                "status": ModuleStatus.AVAILABLE.value,
                "bands": {b: risk_total.get(b, 0) for b in RISK_BANDS},
                "missing_probability": risk_missing_total,
                "band_thresholds": {"low_max": cfg.risk_low_max, "medium_max": cfg.risk_medium_max},
                "source": (f"dataset column '{prob_field}'" if prob_field else "injected probability provider"),
                "note": (
                    "Bands use configured policy thresholds over existing churn probabilities; nothing is re-predicted."
                ),
            }
            if use_probabilities
            else {
                "status": ModuleStatus.BLOCKED_BY_MISSING_DATA.value,
                "bands": None,
                "reason": (
                    "No existing churn probabilities are available (no probability column or provider configured)."
                ),
            }
        ),
        "assumptions": _assumptions(cfg),
        "limitations": _limitations(),
    }


def _thresholds(cfg: LifecycleConfig) -> list[dict[str, Any]]:
    return [{"name": g.name, "min_months": g.min_months, "max_months": g.max_months} for g in cfg.groups]


def _assumptions(cfg: LifecycleConfig) -> list[str]:
    return [
        "Tenure is measured in months as recorded in the dataset; customers with missing, negative or non-numeric "
        "tenure are excluded and counted.",
        "Group boundaries come from configs/experience.yaml (min inclusive, max exclusive).",
        f"Churn rates are shown only for groups with at least {cfg.min_group_size_for_rate} labelled customers.",
        "MonthlyCharges and TotalCharges are billing amounts as recorded; they are not profit or lifetime value.",
        "Blank TotalCharges (new customers) are counted as missing, never filled in.",
    ]


def _limitations() -> list[str]:
    return [
        "This is a tenure proxy. It cannot show what customers did, in what order, or why they left.",
        "Churn labels describe the past snapshot; they do not imply satisfaction or sentiment.",
        "Groups are descriptive and not causal.",
    ]


# Optional helper type for service wiring
ProbabilityProvider = Callable[[], Mapping[str, float]]
