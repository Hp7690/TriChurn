"""Segment intelligence: aggregate ACTUAL Phase 4 business profiles per segment, name, prioritise, derive strategy.

This layer runs AFTER clustering. It consumes ``CustomerBusinessProfile`` objects produced by
``ml.business.BusinessEngine`` (churn probability, CLV, value at risk, ENB, decision, recommended action) and only sums,
averages and counts them. CLV, ENB and retention logic are NOT re-implemented here, and nothing in this module feeds
back into the clustering.

Naming   ``<Value> / <Risk>`` from the segment's average CLV (relative to the portfolio) and average churn probability
         (vs. the configured thresholds). Duplicates are disambiguated by tenure, then by a stable rank of measured
         averages: never by cluster number.
Priority ``sum(w_i * m_i) / sum(w_i)`` over metrics in [0, 1] (value-at-risk share, ENB share, average churn
         probability, intervention rate) with weights from configuration; tiers are score thresholds from configuration.
Strategy the Phase 4 ``recommended_action_id`` mix among the segment's INTERVENE customers; ``no_action`` if none.
"""
from __future__ import annotations

from collections import Counter
from collections.abc import Sequence
from dataclasses import dataclass

import numpy as np
import pandas as pd

from ml.business import INTERVENE, BusinessConfig, CustomerBusinessProfile, assign_risk_band, format_money
from ml.business.schemas import NO_ACTION_ID
from ml.errors import SegmentationConfigError, SegmentationInputError
from ml.segmentation.schemas import (
    MODEL_THRESHOLD,
    CustomerAssignment,
    NamingConfig,
    PriorityConfig,
    SegmentProfile,
    SegmentStrategy,
)


@dataclass(frozen=True)
class _Aggregate:
    """Raw per-segment measurements, before names / priority / strategy are attached."""
    segment_id: int
    count: int
    avg_tenure: float
    avg_monthly: float
    avg_total: float
    avg_prob: float
    avg_clv: float
    total_clv: float
    total_var: float
    total_enb: float
    avg_enb: float
    intervention_count: int


def _mean(values: np.ndarray) -> float:
    """Mean ignoring NaN (e.g. TotalCharges is blank for brand-new customers); NaN only if nothing is known."""
    return float(np.nanmean(values)) if np.isfinite(values).any() else float("nan")


def _column(customers: pd.DataFrame, features_cfg: dict, role: str) -> np.ndarray:
    col = (features_cfg.get("roles") or {}).get(role)
    if not col or col not in customers.columns:
        raise SegmentationInputError(f"Customer data has no '{role}' column (features.yaml roles.{role}={col!r}).")
    return pd.to_numeric(customers[col], errors="coerce").to_numpy(dtype="float64")


def _aggregate(ids: np.ndarray, k: int, tenure: np.ndarray, monthly: np.ndarray, total: np.ndarray,
               profiles: Sequence[CustomerBusinessProfile]) -> list[_Aggregate]:
    prob = np.array([p.churn_probability for p in profiles])
    clv = np.array([p.clv for p in profiles])
    var = np.array([p.value_at_risk for p in profiles])
    enb = np.array([p.expected_net_benefit for p in profiles])
    treat = np.array([p.intervention_decision == INTERVENE for p in profiles])
    out = []
    for s in range(k):
        m = ids == s
        if not m.any():
            raise SegmentationInputError(f"Segment {s} has no customers in the profiled population.")
        out.append(_Aggregate(s, int(m.sum()), _mean(tenure[m]), _mean(monthly[m]), _mean(total[m]),
                              float(prob[m].mean()), float(clv[m].mean()), float(clv[m].sum()), float(var[m].sum()),
                              float(enb[m].sum()), float(enb[m].mean()), int(treat[m].sum())))
    return out


# ------------------------------------------------------------------------------------------------------- naming
def resolve_risk_threshold(naming: NamingConfig, model_threshold: float | None) -> float:
    high = naming.risk_high_min_probability
    if high == MODEL_THRESHOLD:
        if model_threshold is None:
            raise SegmentationInputError(
                "naming.risk.high_min_probability is 'model_threshold' but no model_threshold was supplied.")
        return float(model_threshold)
    return float(high)


def value_label(avg_clv: float, portfolio_avg_clv: float, naming: NamingConfig) -> str:
    ratio = avg_clv / portfolio_avg_clv if portfolio_avg_clv > 0 else 1.0
    if ratio >= naming.value_high_min_ratio:
        return "High Value"
    return "Low Value" if ratio <= naming.value_low_max_ratio else "Mid Value"


def risk_label(avg_prob: float, high_min: float, naming: NamingConfig) -> str:
    if avg_prob >= high_min:
        return "High Risk"
    return "Stable" if avg_prob <= naming.risk_stable_max_probability else "Moderate Risk"


def tenure_label(avg_tenure: float, portfolio_avg_tenure: float, naming: NamingConfig) -> str:
    ratio = avg_tenure / portfolio_avg_tenure if portfolio_avg_tenure > 0 else 1.0
    if ratio >= naming.tenure_established_min_ratio:
        return "Established"
    return "New" if ratio <= naming.tenure_new_max_ratio else "Mid-Tenure"


def name_segments(aggs: Sequence[_Aggregate], naming: NamingConfig, model_threshold: float | None
                  ) -> dict[int, tuple[str, str, str]]:
    """segment_id -> (unique name, value label, risk label). Depends only on measured averages, never on the ids."""
    total_n = sum(a.count for a in aggs)
    p_clv = sum(a.total_clv for a in aggs) / total_n
    p_ten = float(np.nansum([a.avg_tenure * a.count for a in aggs]) / total_n)
    high = resolve_risk_threshold(naming, model_threshold)
    labels = {a.segment_id: (value_label(a.avg_clv, p_clv, naming), risk_label(a.avg_prob, high, naming)) for a in aggs}
    names = {sid: f"{v} / {r}" for sid, (v, r) in labels.items()}
    by_name: dict[str, list[_Aggregate]] = {}
    for a in aggs:
        by_name.setdefault(names[a.segment_id], []).append(a)
    for base, group in by_name.items():
        if len(group) > 1:                                   # disambiguate by tenure first
            for a in group:
                names[a.segment_id] = f"{base} ({tenure_label(a.avg_tenure, p_ten, naming)})"
    by_name = {}
    for a in aggs:
        by_name.setdefault(names[a.segment_id], []).append(a)
    for base, group in by_name.items():
        if len(group) > 1:                                   # still identical: stable rank of measured averages
            ranked = sorted(group, key=lambda a: (-a.avg_clv, -a.avg_tenure, -a.avg_prob, a.segment_id))
            for i, a in enumerate(ranked, start=1):
                names[a.segment_id] = f"{base} #{i}"
    return {sid: (names[sid], *labels[sid]) for sid in names}


# ----------------------------------------------------------------------------------------------------- priority
def priority_scores(aggs: Sequence[_Aggregate], prio: PriorityConfig) -> dict[int, float]:
    """Weighted mean of metrics that all lie in [0, 1]; weights are normalised by their sum."""
    total_var = sum(a.total_var for a in aggs)
    total_enb = sum(a.total_enb for a in aggs)
    w = prio.weights
    wsum = sum(w.values())
    scores = {}
    for a in aggs:
        metrics = {
            "value_at_risk_share": a.total_var / total_var if total_var > 0 else 0.0,
            "total_enb_share": a.total_enb / total_enb if total_enb > 0 else 0.0,
            "avg_churn_probability": a.avg_prob,
            "intervention_rate": a.intervention_count / a.count,
        }
        scores[a.segment_id] = sum(weight * metrics[name] for name, weight in w.items()) / wsum
    return scores


def priority_tier(score: float, prio: PriorityConfig) -> str:
    return next(t.name for t in prio.tiers if score >= t.min_score)


# ----------------------------------------------------------------------------------------------------- strategy
def build_strategy(seg_profiles: Sequence[CustomerBusinessProfile], business: BusinessConfig) -> SegmentStrategy:
    """Segment strategy = the Phase 4 recommendation mix for the segment's INTERVENE customers."""
    treated = [p for p in seg_profiles if p.intervention_decision == INTERVENE]
    if not treated:
        noop = business.actions[NO_ACTION_ID].name
        return SegmentStrategy(
            NO_ACTION_ID, noop, {}, 0,
            f"No customer in this segment meets the Phase 4 intervention policy ({len(seg_profiles)} customers); "
            f"recommended action: {noop}.")
    mix = Counter(p.recommended_action_id for p in treated)
    enb = Counter()
    for p in treated:
        enb[p.recommended_action_id] += p.expected_net_benefit
    primary = min(mix, key=lambda a: (-mix[a], -enb[a], a))
    name = business.actions[primary].name
    total_enb = sum(p.expected_net_benefit for p in treated)
    summary = (f"Phase 4 recommends '{name}' for {mix[primary]} of {len(treated)} customers it would treat "
               f"({len(treated)} of {len(seg_profiles)} in the segment); estimated total expected net benefit of the "
               f"recommended actions {format_money(total_enb, business.currency)} under the configured assumptions "
               "(not a causal estimate).")
    return SegmentStrategy(primary, name, dict(sorted(mix.items())), len(treated), summary)


# ------------------------------------------------------------------------------------------------------ profiles
def profile_segments(
    customers: pd.DataFrame, segment_ids: np.ndarray, business_profiles: Sequence[CustomerBusinessProfile],
    business: BusinessConfig, features_cfg: dict, naming: NamingConfig, priority: PriorityConfig,
    model_threshold: float | None, id_column: str | None = None,
) -> list[SegmentProfile]:
    """One ``SegmentProfile`` per segment for the given customers and their Phase 4 profiles (row-aligned)."""
    ids = np.asarray(segment_ids, dtype=int)
    if not (len(customers) == len(ids) == len(business_profiles)):
        raise SegmentationInputError(
            f"Got {len(customers)} customers, {len(ids)} segment ids and {len(business_profiles)} business profiles.")
    if len(ids) == 0:
        raise SegmentationInputError("Cannot profile segments of an empty customer set.")
    if id_column is not None:
        if id_column not in customers.columns:
            raise SegmentationInputError(f"id column '{id_column}' is not in the customer frame.")
        expected = [str(v) for v in customers[id_column]]
        if expected != [p.customer_id for p in business_profiles]:
            raise SegmentationInputError("Business profiles are not row-aligned with the customer frame (ids differ).")
    k = int(ids.max()) + 1
    aggs = _aggregate(ids, k, _column(customers, features_cfg, "tenure"),
                      _column(customers, features_cfg, "monthly_charges"),
                      _column(customers, features_cfg, "total_charges"), business_profiles)
    names = name_segments(aggs, naming, model_threshold)
    scores = priority_scores(aggs, priority)
    order = sorted(scores, key=lambda s: (-scores[s], -aggs[s].total_var, s))
    rank = {s: i for i, s in enumerate(order, start=1)}
    n = len(ids)
    out = []
    for a in aggs:
        mine = [p for p, s in zip(business_profiles, ids, strict=True) if s == a.segment_id]
        name, v_label, r_label = names[a.segment_id]
        out.append(SegmentProfile(
            segment_id=a.segment_id, segment_name=name, value_label=v_label, risk_label=r_label,
            customer_count=a.count, customer_pct=a.count / n, avg_tenure=a.avg_tenure,
            avg_monthly_charges=a.avg_monthly, avg_total_charges=a.avg_total, avg_churn_probability=a.avg_prob,
            avg_clv=a.avg_clv, total_clv=a.total_clv, total_value_at_risk=a.total_var, avg_enb=a.avg_enb,
            total_enb=a.total_enb, intervention_rate=a.intervention_count / a.count,
            intervention_count=a.intervention_count, risk_band=assign_risk_band(a.avg_prob, business.risk_bands),
            priority_score=scores[a.segment_id], priority_rank=rank[a.segment_id],
            priority_tier=priority_tier(scores[a.segment_id], priority), strategy=build_strategy(mine, business)))
    return out


def build_assignments(customer_ids: Sequence[str | None], segment_ids: np.ndarray, distances: np.ndarray,
                      profiles: Sequence[SegmentProfile]) -> list[CustomerAssignment]:
    """Per-customer assignment: id, segment, segment name and the clustering distance to its centroid."""
    names = {p.segment_id: p.segment_name for p in profiles}
    missing = set(np.asarray(segment_ids).tolist()) - set(names)
    if missing:
        raise SegmentationConfigError(f"No profile (name) for segment ids {sorted(missing)}.")
    return [CustomerAssignment(None if cid is None else str(cid), int(s), names[int(s)], float(d))
            for cid, s, d in zip(customer_ids, segment_ids, distances, strict=True)]
