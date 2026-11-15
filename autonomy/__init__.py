"""TriChurn Phase 11 - Autonomous Retention Intelligence (framework-free domain package).

A controlled, explainable, auditable layer on top of the locked Phase 2/4/5 pipeline and the Phase 9 portfolio.
It generates recommendations with deterministic rules, detects risk changes between batch snapshots, and records a
human-approval workflow, feedback and an append-only audit trail. It never contacts customers or external systems and
it trains no model.

Important distinctions kept throughout: churn probability is NOT uplift; a high-risk customer is not necessarily
persuadable; estimated impact (Phase 4, assumed success rates) is NOT observed saved revenue.
"""
from __future__ import annotations

__version__ = "11.0.0"

ESTIMATE_NOTE = ("Estimated figures use the Phase 4 assumed action costs and success rates. They are not observed "
                 "results and not causal uplift estimates.")
