"""What each module needs before it can run, stated in plain language for the Experience Command Center.

These are requirements, not data. ``dataset_kind`` names the schema (see ``schemas.build_schemas``) the file must meet.
"""

from __future__ import annotations

from typing import Any

MODULES: dict[str, dict[str, Any]] = {
    "lifecycle": {
        "title": "Customer lifecycle (tenure proxy)",
        "dataset_kind": None,
        "needs": [
            "A customer table with a numeric tenure (months) column.",
            "Optional: Contract, MonthlyCharges, TotalCharges, Churn; and existing churn probabilities for the "
            "risk distribution.",
        ],
        "note": "Runs on the Telco dataset. This is a tenure-based proxy, not an event-based journey.",
    },
    "feedback": {
        "title": "Customer feedback data",
        "dataset_kind": "feedback",
        "needs": [
            "A CSV or JSON file of real customer feedback with feedback_id, customer_id, feedback_text and "
            "submitted_at (ISO 8601).",
            "Optional: channel, and sentiment_label (human-assigned) for training or evaluation.",
        ],
        "note": "Place the file inside the experience data directory and name it under datasets.feedback in "
        "configs/experience.yaml.",
    },
    "sentiment": {
        "title": "Sentiment intelligence",
        "dataset_kind": "feedback",
        "needs": [
            "A validated feedback dataset (above).",
            "Enough human-labelled records (configurable minimum) to train and evaluate a model.",
            "A documented model implementing the SentimentModel interface, registered in code.",
        ],
        "note": "No model is trained or shipped in Phase 13. Churn probability and Telco columns are never used as "
        "sentiment inputs.",
    },
    "complaints": {
        "title": "Complaint intelligence",
        "dataset_kind": "tickets",
        "needs": [
            "A CSV or JSON export from a real ticketing system with ticket_id, customer_id, category, severity, "
            "status and created_at.",
            "Optional: resolved_at and sla_due_at (enable resolution-time and SLA analytics).",
        ],
        "note": "TechSupport (a subscription flag in Telco) is not a complaint and is never used as one.",
    },
    "nps": {
        "title": "Net Promoter Score",
        "dataset_kind": "nps",
        "needs": ["NPS survey responses with response_id, customer_id, score (0-10 by default) and survey_date."],
        "note": "NPS = % promoters - % detractors over valid responses.",
    },
    "csat": {
        "title": "Customer satisfaction (CSAT)",
        "dataset_kind": "csat",
        "needs": ["CSAT survey responses with response_id, customer_id, score (1-5 by default) and survey_date."],
        "note": "CSAT = satisfied responses / valid responses; the satisfied threshold is configurable.",
    },
    "journey": {
        "title": "Customer journey",
        "dataset_kind": "events",
        "needs": [
            "Timestamped events with customer_id, event_type, event_timestamp and channel.",
            "Optional: event_id and a JSON metadata object.",
        ],
        "note": "Tenure groups are not events and are never presented as a journey.",
    },
}
