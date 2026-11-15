"""Framework-free orchestration for Phase 11. Raises only ``autonomy.errors`` (plus Phase 9's PortfolioUnavailable)."""
from __future__ import annotations

import hashlib
import json
import re
from collections.abc import Callable, Mapping, Sequence
from dataclasses import asdict, dataclass
from datetime import UTC, date, datetime
from typing import Any

from autonomy import ESTIMATE_NOTE
from autonomy.agent import generate
from autonomy.auth import Authorizer, DenyAllAuthorizer, Reviewer
from autonomy.config import AutonomyConfig
from autonomy.errors import (
    AutonomyConflictError,
    AutonomyForbiddenError,
    AutonomyInputError,
    AutonomyNotFoundError,
    FeatureDisabledError,
)
from autonomy.models import (
    APPROVED,
    CANCELLED,
    EXECUTED,
    FAILED,
    OUTCOMES,
    PENDING,
    REJECTED,
    STATUSES,
    AuditEvent,
    Feedback,
    Page,
    Recommendation,
)
from autonomy.monitor import ScanResult, scan
from autonomy.source import RetentionSource
from autonomy.store import AutonomyStore, new_id
from retention.models import INTERVENE

# transition name -> (allowed current statuses, target status)
ACTIONS: dict[str, tuple[tuple[str, ...], str]] = {
    "approve": ((PENDING,), APPROVED),
    "reject": ((PENDING,), REJECTED),
    "cancel": ((PENDING, APPROVED), CANCELLED),
    "execute": ((APPROVED,), EXECUTED),
    "fail": ((APPROVED,), FAILED),
}
TRAINER_AVAILABLE = False        # no model-training code exists in Phase 11, so learning can never be enabled by config
_ID = re.compile(r"^[A-Za-z0-9_.\-]{1,64}$")
_SOURCE = re.compile(r"^[A-Za-z0-9_ .\-]{1,60}$")
_KEY = re.compile(r"^[A-Za-z0-9_.\-]{8,100}$")
ANONYMOUS = "anonymous"


@dataclass(frozen=True)
class GenerateReport:
    considered: int
    created: int
    skipped_existing: int
    rules_version: str
    note: str


@dataclass(frozen=True)
class RecommendationDetail:
    recommendation: Recommendation
    audit: tuple[AuditEvent, ...]


@dataclass(frozen=True)
class TransitionResult:
    recommendation: Recommendation
    replayed: bool


@dataclass(frozen=True)
class FeedbackResult:
    feedback: Feedback
    replayed: bool


class AutonomyFacade:
    def __init__(self, source: RetentionSource, store: AutonomyStore, config: AutonomyConfig,
                 authorizer: Authorizer | None = None, clock: Callable[[], datetime] | None = None):
        self._source, self._store, self._config = source, store, config
        self._auth = authorizer or DenyAllAuthorizer()
        self._clock = clock or (lambda: datetime.now(UTC))

    # ------------------------------------------------------------------------------------------ helpers
    def _now(self) -> str:
        return self._clock().isoformat(timespec="seconds")

    def _paging(self, page: int, size: int | None) -> tuple[int, int]:
        size = size or self._config.default_page_size
        if page < 1 or not 1 <= size <= self._config.max_page_size:
            raise AutonomyInputError(f"page must be >= 1 and page_size between 1 and {self._config.max_page_size}.")
        return page, size

    @staticmethod
    def _check(value: str | None, allowed: Sequence[str], name: str) -> None:
        if value is not None and value not in allowed:
            raise AutonomyInputError(f"{name} must be one of {', '.join(allowed)}.")

    def authenticate(self, headers: Mapping[str, str]) -> Reviewer | None:
        return self._auth.authenticate(headers)

    def _require_reviewer(self, reviewer: Reviewer | None, attempted: str, rec_id: str | None) -> Reviewer:
        """Approvals are a consequential workflow: they need the feature flag AND an authenticated reviewer."""
        if not self._config.approvals_enabled:
            raise FeatureDisabledError("The approval workflow is disabled in configuration.")
        if reviewer is None or not self._auth.configured:
            self._store.add_audit("authorization_denied", rec_id, None, ANONYMOUS, False, f"attempted: {attempted}",
                                  self._now())
            raise AutonomyForbiddenError(
                "An authenticated reviewer is required. No identity provider is configured for this API, so this "
                "action is disabled.")
        return reviewer

    def _idempotency(self, key: str | None, endpoint: str, payload: Mapping[str, Any], required: bool
                     ) -> tuple[str | None, str | None]:
        """Returns (request_hash, stored_response_json). Raises on a missing key or a reused key with another body."""
        if key is None:
            if required:
                raise AutonomyInputError("An Idempotency-Key header (8-100 characters) is required.")
            return None, None
        if not _KEY.match(key):
            raise AutonomyInputError("Idempotency-Key must be 8-100 characters of letters, digits, '_', '.', '-'.")
        digest = hashlib.sha256(json.dumps(payload, sort_keys=True).encode()).hexdigest()
        stored = self._store.get_idempotent(key, endpoint)
        if stored is not None and stored[0] != digest:
            raise AutonomyConflictError("This Idempotency-Key was already used with a different request.")
        return digest, None if stored is None else stored[1]

    # -------------------------------------------------------------------------------------------- status
    def status(self) -> dict[str, Any]:
        c = self._config
        return {
            "agent_enabled": c.agent_enabled, "monitoring_enabled": c.monitoring_enabled,
            "monitoring_mode": "batch_snapshot_comparison (no live event source exists)",
            "approvals_enabled_in_config": c.approvals_enabled, "identity_provider_configured": self._auth.configured,
            "approvals_available": c.approvals_enabled and self._auth.configured,
            "execution_integration": "none: 'executed' is a manual record; nothing is sent to customers or systems",
            "learning_enabled": c.learning_enabled and TRAINER_AVAILABLE, "rules_version": c.rules_version}

    # ----------------------------------------------------------------------------------------- monitoring
    def scan_risks(self) -> ScanResult:
        if not self._config.monitoring_enabled:
            raise FeatureDisabledError("Risk monitoring is disabled in configuration.")
        result = scan(self._source.portfolio(), self._store, self._config, self._now)
        self._store.add_audit("risk_scan", None, None, "system", False,
                              f"{result.status}: {result.events_created} new, {result.events_resolved} resolved",
                              self._now())
        return result

    def list_risks(self, risk_level: str | None, status: str | None, page: int, page_size: int | None) -> Page:
        page, size = self._paging(page, page_size)
        self._check(risk_level, ("LOW", "MEDIUM", "HIGH", "CRITICAL"), "risk_level")
        self._check(status, ("new", "resolved"), "status")
        return self._store.list_events(risk_level, status, page, size)

    # ------------------------------------------------------------------------------- recommendations
    def generate_recommendations(self, customer_ids: Sequence[str] | None, limit: int | None) -> GenerateReport:
        if not self._config.agent_enabled:
            raise FeatureDisabledError("The retention agent is disabled in configuration.")
        cap = self._config.max_recommendations_per_request
        if limit is not None and not 1 <= limit <= cap:
            raise AutonomyInputError(f"limit must be between 1 and {cap}.")
        portfolio = self._source.portfolio()
        if customer_ids:
            entries = []
            for cid in dict.fromkeys(customer_ids):
                if not _ID.match(cid):
                    raise AutonomyInputError("customer ids may only contain letters, digits, '_', '.', '-'.")
                entry = self._source.entry(cid)
                if entry is None:
                    raise AutonomyNotFoundError("A requested customer is not in the scored portfolio.")
                entries.append(entry)
            if len(entries) > cap:
                raise AutonomyInputError(f"At most {cap} customers can be evaluated per request.")
        else:
            entries = list(self._source.entries())[: limit or cap]
        drafts = generate(entries, portfolio, self._config, self._now)
        created = self._store.add_recommendations([(d.recommendation, d.fingerprint) for d in drafts],
                                                  "agent:" + self._config.rules_version, self._now())
        report = GenerateReport(len(entries), created, len(drafts) - created, self._config.rules_version,
                                "Deterministic rules over verified Phase 4/9 results. Nothing was sent or executed.")
        self._store.add_audit("generation_run", None, None, "agent", False,
                              f"considered {report.considered}, created {created}", self._now())
        return report

    def list_recommendations(self, status: str | None, category: str | None, priority: str | None,
                             risk_band: str | None, customer_id: str | None, page: int,
                             page_size: int | None) -> Page:
        page, size = self._paging(page, page_size)
        self._check(status, STATUSES, "status")
        return self._store.list_recommendations(status, category, priority, risk_band, customer_id, page, size)

    def get_recommendation(self, recommendation_id: str) -> RecommendationDetail:
        rec = self._store.get_recommendation(recommendation_id)
        if rec is None:
            raise AutonomyNotFoundError("Recommendation not found.")
        trail = self._store.list_audit(None, recommendation_id, None, 1, 100).items
        return RecommendationDetail(rec, tuple(trail))

    # ---------------------------------------------------------------------------------------- workflow
    def _validate_eligibility(self, rec: Recommendation) -> None:
        """Re-check against the CURRENT portfolio before approving/executing; stale recommendations are refused."""
        if rec.rules_version != self._config.rules_version:
            raise AutonomyConflictError("This recommendation was created under older rules; generate it again.")
        customer = self._source.portfolio().get(rec.customer_id)
        if customer is None:
            raise AutonomyConflictError("The customer is no longer in the scored portfolio.")
        if rec.rule_id == "R1":
            option = next((o for o in customer.options if o.action_id == rec.action_id), None)
            if customer.decision != INTERVENE or option is None or not option.eligible:
                raise AutonomyConflictError("The Phase 4 action is no longer eligible for this customer.")

    def transition(self, recommendation_id: str, action: str, reviewer: Reviewer | None, note: str | None,
                   idempotency_key: str | None) -> TransitionResult:
        if action not in ACTIONS:
            raise AutonomyInputError("Unknown workflow action.")
        who = self._require_reviewer(reviewer, action, recommendation_id)
        clean = self._clean_note(note)
        digest, stored = self._idempotency(idempotency_key, f"transition:{action}:{recommendation_id}",
                                           {"reviewer": who.user_id, "note": clean}, required=True)
        current = self._store.get_recommendation(recommendation_id)
        if current is None:
            raise AutonomyNotFoundError("Recommendation not found.")
        if stored is not None:
            return TransitionResult(current, True)
        allowed_from, target = ACTIONS[action]
        if current.status not in allowed_from:
            raise AutonomyConflictError(f"A '{current.status}' recommendation cannot be '{target}'.")
        if action in ("approve", "execute"):
            try:
                self._validate_eligibility(current)
            except AutonomyConflictError as exc:
                self._store.add_audit("eligibility_failed", recommendation_id, current.customer_id, who.user_id, True,
                                      str(exc), self._now())
                raise
        updated = self._store.transition(recommendation_id, allowed_from, target, who.user_id, True,
                                         clean or action, self._now())
        assert digest is not None and idempotency_key is not None
        self._store.put_idempotent(idempotency_key, f"transition:{action}:{recommendation_id}", digest,
                                   json.dumps({"status": updated.status}), self._now())
        return TransitionResult(updated, False)

    def _clean_note(self, note: str | None) -> str:
        if note is None or not note.strip():
            return ""
        text = note.strip()
        if len(text) > self._config.note_max_length or any(ord(ch) < 32 for ch in text):
            raise AutonomyInputError(f"note must be at most {self._config.note_max_length} characters, no control "
                                     "characters.")
        return text

    # ---------------------------------------------------------------------------------------- feedback
    def record_feedback(self, reviewer: Reviewer | None, recommendation_id: str, outcome: str, outcome_at: str,
                        campaign_id: str | None, data_source: str, idempotency_key: str | None) -> FeedbackResult:
        who = self._require_reviewer(reviewer, "record_feedback", recommendation_id)
        self._check(outcome, OUTCOMES, "outcome")
        if not _SOURCE.match(data_source or ""):
            raise AutonomyInputError("data_source must be 1-60 letters, digits, spaces, '_', '.', '-'.")
        if campaign_id is not None and not _ID.match(campaign_id):
            raise AutonomyInputError("campaign_id contains invalid characters.")
        try:
            outcome_day = date.fromisoformat(outcome_at[:10])
        except (TypeError, ValueError) as exc:
            raise AutonomyInputError("outcome_at must be an ISO date (YYYY-MM-DD).") from exc
        digest, stored = self._idempotency(idempotency_key, f"feedback:{recommendation_id}", {
            "outcome": outcome, "outcome_at": outcome_day.isoformat(), "campaign_id": campaign_id,
            "data_source": data_source}, required=True)
        rec = self._store.get_recommendation(recommendation_id)
        if rec is None:
            raise AutonomyNotFoundError("Recommendation not found.")
        existing = next((f for f in self._store.list_feedback(1, self._config.max_page_size).items
                         if f.recommendation_id == recommendation_id), None)
        if stored is not None and existing is not None:
            return FeedbackResult(existing, True)
        if rec.status != EXECUTED:
            raise AutonomyConflictError("Observed outcomes can only be recorded for executed recommendations.")
        if outcome_day > self._clock().date():
            raise AutonomyInputError("outcome_at cannot be in the future.")
        if outcome_day < date.fromisoformat(rec.created_at[:10]):
            raise AutonomyInputError("outcome_at cannot be before the recommendation was created.")
        fb = Feedback(new_id("fbk"), recommendation_id, rec.customer_id, rec.action_name or rec.category, rec.status,
                      campaign_id, outcome, outcome_day.isoformat(), data_source.strip(), True, who.user_id,
                      self._now())
        self._store.add_feedback(fb, self._now())
        assert digest is not None and idempotency_key is not None
        self._store.put_idempotent(idempotency_key, f"feedback:{recommendation_id}", digest,
                                   json.dumps({"feedback_id": fb.feedback_id}), self._now())
        return FeedbackResult(fb, False)

    def list_feedback(self, page: int, page_size: int | None) -> Page:
        page, size = self._paging(page, page_size)
        return self._store.list_feedback(page, size)

    def learning_report(self) -> dict[str, Any]:
        stats = self._store.feedback_stats()
        total = sum(n for _, _, n in stats)
        by_action: dict[str, dict[str, int]] = {}
        for action, outcome, n in stats:
            by_action.setdefault(action or "unknown", {})[outcome] = n
        per_action = {a: sum(o.values()) for a, o in by_action.items()}
        c = self._config
        enough_total = total >= c.min_validated_outcomes
        enough_each = bool(per_action) and all(n >= c.min_outcomes_per_action for n in per_action.values())
        return {
            "validated_outcomes": total,
            "by_action": [{"action": a, "outcomes": dict(sorted(o.items())), "total": sum(o.values()),
                           "observed_retained_share": (o.get("retained", 0) / sum(o.values()))} for a, o in
                          sorted(by_action.items())],
            "observed_vs_estimated": ("Observed outcomes only. Estimated Phase 4 impact is never mixed into these "
                                      "figures."),
            "checks": [
                {"code": "enough_total_outcomes", "passed": enough_total,
                 "detail": f"{total} validated outcomes (minimum {c.min_validated_outcomes})."},
                {"code": "enough_outcomes_per_action", "passed": enough_each,
                 "detail": f"Each action needs at least {c.min_outcomes_per_action} outcomes."},
                {"code": "control_group_present", "passed": False,
                 "detail": "Phase 11 feedback has no control group, so causal/uplift learning is not possible."}],
            "learning_enabled": c.learning_enabled and TRAINER_AVAILABLE,
            "status": "NOT_ENABLED",
            "note": ("Model learning is not enabled: no training or deployment code exists in Phase 11 and no model is "
                     "retrained automatically. Collected feedback supports offline evaluation only. Observed retention "
                     "shares are descriptive, not causal effects.")}

    # --------------------------------------------------------------------------------------- audit/summary
    def list_audit(self, event_type: str | None, recommendation_id: str | None, customer_id: str | None,
                   page: int, page_size: int | None) -> Page:
        page, size = self._paging(page, page_size)
        return self._store.list_audit(event_type, recommendation_id, customer_id, page, size)

    def summary(self) -> dict[str, Any]:
        counts = self._store.recommendation_counts()
        pending = self._store.pending_estimates()
        estimated = [p.get("phase4", {}).get("estimated_net_benefit", 0.0) for p in pending if p.get("phase4")]
        latest = self._store.latest_snapshot()
        events = self._store.event_counts()
        return {
            "status": self.status(), "recommendations": counts,
            "open_risk_events": {k.split(":")[0]: n for k, n in events.items() if k.endswith(":new")},
            "latest_snapshot": None if latest is None else asdict(latest),
            "estimated": {"pending_recommendations_with_phase4_estimate": len(estimated),
                          "estimated_net_benefit_pending": round(sum(estimated), 2), "is_estimate": True,
                          "note": ESTIMATE_NOTE},
            "observed": {"validated_outcomes": sum(n for _, _, n in self._store.feedback_stats())},
            "store": self._store.counts()}
