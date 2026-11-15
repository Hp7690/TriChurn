"""Uplift READINESS checks only. No uplift model is built, trained or evaluated here.

Uplift (causal) modelling needs customers who were randomly assigned to receive a campaign (treatment) or not
(control) plus their observed outcomes. This module inspects (a) the source dataset's columns and (b) the campaign
database and reports, with plain reasons, whether that evidence exists. It never fabricates any of it.
"""
from __future__ import annotations

import re
from collections.abc import Iterable
from dataclasses import dataclass

from retention.analytics import OBSERVATION_NOTE
from retention.campaign_store import AssignmentRecord, Campaign
from retention.config import UpliftReadinessConfig

TREATMENT_HINTS = re.compile(r"(treat|campaign|offer|contact|control|holdout|intervention|uplift|promo|outreach)", re.I)

REQUIREMENTS = (
    "A treatment indicator per customer (who received a retention action) and a control group that did not.",
    "Random assignment between treatment and control (or a documented quasi-experimental design).",
    "A recorded outcome (retained / churned) for both groups over the same observation window.",
    "Enough customers in each group to measure an effect (see configured minimums).",
    "Customer features captured BEFORE treatment so models cannot learn from post-treatment information.",
)


@dataclass(frozen=True)
class ReadinessCheck:
    code: str
    passed: bool
    detail: str


@dataclass(frozen=True)
class UpliftReadiness:
    ready: bool
    status: str                       # "NOT_READY" or "READY_FOR_FEASIBILITY_REVIEW"
    dataset_treatment_columns: tuple[str, ...]
    treatment_assignments: int
    control_assignments: int
    unspecified_assignments: int
    outcomes_recorded: int
    checks: tuple[ReadinessCheck, ...]
    requirements: tuple[str, ...] = REQUIREMENTS
    note: str = ("No uplift model exists and none is claimed. Even when READY, a statistician must review the design "
                 "before modelling. " + OBSERVATION_NOTE)


def assess(dataset_columns: Iterable[str] | None, campaigns: list[Campaign], assignments: list[AssignmentRecord],
           config: UpliftReadinessConfig) -> UpliftReadiness:
    inspected = dataset_columns is not None
    columns = tuple(sorted(c for c in (dataset_columns or ()) if TREATMENT_HINTS.search(c)))
    treatment = [a for a in assignments if a.assignment_group == "treatment"]
    control = [a for a in assignments if a.assignment_group == "control"]
    unspecified = [a for a in assignments if a.assignment_group == "unspecified"]
    recorded = [a for a in assignments if a.outcome is not None]
    coverage = len(recorded) / len(assignments) if assignments else 0.0
    randomized_ids = {c.campaign_id for c in campaigns if c.randomized}
    randomized_ok = bool(assignments) and all(a.campaign_id in randomized_ids for a in treatment + control) \
        and bool(treatment + control)

    checks = (
        ReadinessCheck("dataset_has_treatment_columns", bool(columns),
                       "Treatment-like columns found: " + ", ".join(columns) if columns
                       else "The source dataset has no treatment, campaign or outcome-of-campaign columns."
                       if inspected else "The source dataset could not be inspected right now."),
        ReadinessCheck("treatment_group_size", len(treatment) >= config.min_customers_per_arm,
                       f"{len(treatment)} treatment assignments recorded (minimum {config.min_customers_per_arm})."),
        ReadinessCheck("control_group_size", len(control) >= config.min_customers_per_arm,
                       f"{len(control)} control assignments recorded (minimum {config.min_customers_per_arm})."),
        ReadinessCheck("outcome_coverage", bool(assignments) and coverage >= config.min_outcome_coverage,
                       f"{coverage:.0%} of assignments have a recorded outcome "
                       f"(minimum {config.min_outcome_coverage:.0%})."),
        ReadinessCheck("randomized_assignment",
                       randomized_ok or not config.require_randomized_assignment,
                       "Treatment and control assignments belong to campaigns marked randomised."
                       if randomized_ok else "No randomised treatment/control campaign is recorded."))
    # The dataset columns check informs but does not by itself make the project ready: campaign evidence is required.
    ready = all(c.passed for c in checks[1:])
    return UpliftReadiness(
        ready=ready, status="READY_FOR_FEASIBILITY_REVIEW" if ready else "NOT_READY",
        dataset_treatment_columns=columns, treatment_assignments=len(treatment), control_assignments=len(control),
        unspecified_assignments=len(unspecified), outcomes_recorded=len(recorded), checks=checks)
