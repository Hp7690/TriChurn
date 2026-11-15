"""Phase 13: sentiment / complaint / journey foundations. Fixtures here are TEST-ONLY and never reach the app."""

from __future__ import annotations

from datetime import UTC, datetime

import pytest

from trichurn_experience.complaints import SeverityClassifier, aggregate_complaints, sla_state
from trichurn_experience.config import ComplaintConfig, SentimentConfig, parse_config
from trichurn_experience.journey import (
    JourneyEvent,
    aggregate_journeys,
    build_sequences,
    customer_sequence,
    deduplicate,
    to_events,
)
from trichurn_experience.schemas import BlockedByMissingData, ModuleStatus
from trichurn_experience.sentiment import (
    DefaultTextNormalizer,
    SentimentModel,
    SentimentModelMetadata,
    SentimentPrediction,
    evaluate_predictions,
    predict_texts,
    sentiment_readiness,
)

NOW = datetime(2026, 11, 11, 12, 0, tzinfo=UTC)
LABELS = ("positive", "neutral", "negative")


# ------------------------------------------------------------------------------------------------ sentiment
def test_sentiment_is_blocked_without_feedback_even_with_a_model():
    status, reason = sentiment_readiness(
        feedback_valid_records=0, labelled_records=0, cfg=SentimentConfig(), model=None
    )
    assert status is ModuleStatus.BLOCKED_BY_MISSING_DATA and "no feedback text" in reason


class _FakeModel:
    metadata = SentimentModelMetadata("test-only", "0", "2026-01-01T00:00:00Z", LABELS, "a" * 64, 10)

    def __init__(self):
        self.seen = []

    def predict(self, feedback_ids, texts):
        self.seen = list(texts)
        return [
            SentimentPrediction(i, "neutral", 0.5, {"positive": 0.25, "neutral": 0.5, "negative": 0.25})
            for i in feedback_ids
        ]


def test_sentiment_readiness_levels():
    cfg = SentimentConfig(min_labelled_records=10)
    assert (
        sentiment_readiness(feedback_valid_records=50, labelled_records=3, cfg=cfg, model=None)[0]
        is ModuleStatus.PARTIALLY_AVAILABLE
    )
    assert (
        sentiment_readiness(feedback_valid_records=50, labelled_records=30, cfg=cfg, model=None)[0]
        is ModuleStatus.PARTIALLY_AVAILABLE
    )
    assert (
        sentiment_readiness(feedback_valid_records=50, labelled_records=30, cfg=cfg, model=_FakeModel())[0]
        is ModuleStatus.AVAILABLE
    )


def test_predict_requires_a_registered_model():
    with pytest.raises(BlockedByMissingData):
        predict_texts(None, DefaultTextNormalizer(), ["f1"], ["text"])


def test_predict_normalises_text_and_returns_schema_objects():
    model = _FakeModel()
    assert isinstance(model, SentimentModel)
    out = predict_texts(model, DefaultTextNormalizer(), ["f1"], ["  GREAT\u00a0Service \n"])
    assert model.seen == ["great service"] and out[0].label == "neutral"


def test_predict_rejects_structured_input_and_length_mismatch():
    with pytest.raises(TypeError):
        predict_texts(_FakeModel(), DefaultTextNormalizer(), ["f1"], [{"MonthlyCharges": 70}])  # type: ignore[list-item]
    with pytest.raises(ValueError):
        predict_texts(_FakeModel(), DefaultTextNormalizer(), ["f1", "f2"], ["x"])


@pytest.mark.parametrize(
    "kwargs",
    [
        dict(feedback_id="", label="positive", confidence=0.5),
        dict(feedback_id="f", label="", confidence=0.5),
        dict(feedback_id="f", label="positive", confidence=1.2),
        dict(feedback_id="f", label="positive", confidence=float("nan")),
        dict(feedback_id="f", label="positive", confidence=0.5, scores={"positive": 0.9, "negative": 0.3}),
        dict(feedback_id="f", label="neutral", confidence=0.5, scores={"positive": 0.5, "negative": 0.5}),
    ],
)
def test_prediction_schema_validation(kwargs):
    with pytest.raises(ValueError):
        SentimentPrediction(**kwargs)


def test_model_metadata_validation():
    ok = dict(
        name="m",
        version="1",
        trained_at="2026-01-01",
        labels=LABELS,
        training_dataset_sha256="b" * 64,
        training_records=5,
    )
    SentimentModelMetadata(**ok).validate()
    for bad in ({"labels": ("only",)}, {"training_records": 0}, {"training_dataset_sha256": "xyz"}, {"name": ""}):
        with pytest.raises(ValueError):
            SentimentModelMetadata(**{**ok, **bad}).validate()


def test_evaluation_metrics_from_a_known_confusion_matrix():
    y_true = ["positive", "positive", "neutral", "negative", "negative", "negative"]
    y_pred = ["positive", "neutral", "neutral", "negative", "negative", "positive"]
    rep = evaluate_predictions(y_true, y_pred, LABELS)
    assert rep.n_evaluated == 6 and rep.accuracy == pytest.approx(0.6667, abs=1e-4)
    assert rep.confusion_matrix == [[1, 1, 0], [0, 1, 0], [1, 0, 2]]
    assert rep.per_class["negative"] == {"precision": 1.0, "recall": 0.6667, "f1": 0.8, "support": 3}
    assert rep.to_dict()["labels"] == list(LABELS)


def test_evaluation_rejects_empty_mismatched_and_unknown_labels():
    with pytest.raises(BlockedByMissingData):
        evaluate_predictions([], [], LABELS)
    with pytest.raises(ValueError):
        evaluate_predictions(["positive"], [], LABELS)
    with pytest.raises(ValueError):
        evaluate_predictions(["happy"], ["positive"], LABELS)


def test_text_normalizer_behaviour():
    n = DefaultTextNormalizer(max_chars=10)
    assert n.normalize("  Ａbc\x00\x07   DEF  ") == "abc def"
    assert len(n.normalize("x" * 50)) == 10
    assert DefaultTextNormalizer(lowercase=False).normalize("AbC") == "AbC"
    with pytest.raises(TypeError):
        n.normalize(5)  # type: ignore[arg-type]


# ------------------------------------------------------------------------------------------------ complaints
CCFG = ComplaintConfig(min_records=3)


def ticket(
    tid,
    status="open",
    severity="high",
    category="billing",
    created="2026-10-01T00:00:00Z",
    resolved="",
    due="",
    cid="C1",
):
    return {
        "ticket_id": tid,
        "customer_id": cid,
        "category": category,
        "severity": severity,
        "status": status,
        "created_at": created,
        "resolved_at": resolved,
        "sla_due_at": due,
    }


def test_complaints_blocked_without_tickets():
    with pytest.raises(BlockedByMissingData):
        aggregate_complaints([], CCFG, now=NOW)


def test_sla_states():
    met = ticket("1", "resolved", resolved="2026-10-02T00:00:00Z", due="2026-10-03T00:00:00Z")
    late = ticket("2", "closed", resolved="2026-10-05T00:00:00Z", due="2026-10-03T00:00:00Z")
    overdue = ticket("3", "open", due="2026-10-03T00:00:00Z")
    pending = ticket("4", "in_progress", due="2026-12-01T00:00:00Z")
    nosla = ticket("5")
    assert [sla_state(t, CCFG, NOW) for t in (met, late, overdue, pending, nosla)] == [
        "met",
        "breached",
        "breached",
        "at_risk_open",
        "no_sla",
    ]


def test_complaint_aggregation_counts_resolution_time_and_sla():
    tickets = [
        ticket(
            "1", "resolved", "high", "billing", resolved="2026-10-01T10:00:00Z", due="2026-10-02T00:00:00Z", cid="C1"
        ),
        ticket("2", "closed", "low", "network", resolved="2026-10-02T00:00:00Z", due="2026-10-01T12:00:00Z", cid="C2"),
        ticket("3", "open", "critical", "billing", due="2026-10-03T00:00:00Z", cid="C2"),
        ticket("4", "open", "low", "", cid="C3"),
    ]
    res = aggregate_complaints(tickets, CCFG, now=NOW)
    assert res["tickets_total"] == 4 and res["customers_with_tickets"] == 3
    assert res["by_category"] == {"billing": 2, "network": 1, "Unspecified": 1}
    assert res["by_severity"] == {"low": 2, "medium": 0, "high": 1, "critical": 1}
    assert res["by_status"]["open"] == 2 and res["by_status"]["resolved"] == 1
    assert res["resolution_hours"] == {"count": 2, "median": 17.0, "mean": 17.0}  # 10h and 24h
    assert res["sla"] == {
        "tickets_with_sla": 3,
        "met": 1,
        "breached": 2,
        "open_within_sla": 0,
        "no_sla_field": 1,
        "breach_rate_pct": 66.67,
    }
    assert res["low_sample"] is False and res["as_of"] == NOW.isoformat()


def test_complaint_sample_flag_and_no_resolution_data():
    res = aggregate_complaints([ticket("1")], CCFG, now=NOW)
    assert res["low_sample"] is True and res["resolution_hours"] is None and res["sla"]["breach_rate_pct"] is None


def test_severity_classifier_is_an_interface_only():
    class Rule:
        def classify(self, ticket):
            return "low"

    assert isinstance(Rule(), SeverityClassifier)
    assert not isinstance(object(), SeverityClassifier)


# ------------------------------------------------------------------------------------------------ journey
def ev(cid, etype, ts, channel="app", eid=None):
    return {
        "customer_id": cid,
        "event_type": etype,
        "event_timestamp": ts,
        "channel": channel,
        **({"event_id": eid} if eid else {}),
    }


def test_journey_blocked_without_events():
    with pytest.raises(BlockedByMissingData):
        aggregate_journeys([])


def test_sequences_are_ordered_by_timestamp_per_customer():
    events = to_events(
        [
            ev("A", "purchase", "2026-10-02T10:00:00Z"),
            ev("A", "login", "2026-10-01T10:00:00Z"),
            ev("B", "login", "2026-10-03T10:00:00Z"),
        ]
    )
    seq = build_sequences(events)
    assert [e.event_type for e in seq["A"]] == ["login", "purchase"] and list(seq) == ["A", "B"]
    assert [e.event_type for e in customer_sequence(events, "A")] == ["login", "purchase"]
    assert customer_sequence(events, "ZZZ") == []


def test_equal_timestamps_keep_input_order():
    events = to_events([ev("A", "first", "2026-10-01T10:00:00Z"), ev("A", "second", "2026-10-01T10:00:00Z", "web")])
    assert [e.event_type for e in build_sequences(events)["A"]] == ["first", "second"]


def test_duplicate_events_are_dropped_by_id_or_composite_key():
    events = to_events(
        [
            ev("A", "login", "2026-10-01T10:00:00Z", eid="e1"),
            ev("A", "login", "2026-10-05T10:00:00Z", eid="e1"),
            ev("A", "x", "2026-10-01T10:00:00Z"),
            ev("A", "x", "2026-10-01T10:00:00Z"),
            ev("A", "x", "2026-10-01T10:00:00Z", "web"),
        ]
    )
    kept, dropped = deduplicate(events)
    assert dropped == 2 and len(kept) == 3


def test_journey_aggregation_counts_and_transitions():
    rows = [
        ev("A", "signup", "2026-10-01T00:00:00Z"),
        ev("A", "login", "2026-10-02T00:00:00Z"),
        ev("A", "purchase", "2026-10-03T00:00:00Z", "web"),
        ev("B", "signup", "2026-10-01T00:00:00Z"),
        ev("B", "login", "2026-10-04T00:00:00Z"),
        ev("B", "login", "2026-10-04T00:00:00Z"),
    ]
    res = aggregate_journeys(to_events(rows), min_events=3)
    assert res["events_total"] == 5 and res["duplicate_events_dropped"] == 1 and res["customers"] == 2
    assert res["by_event_type"] == {"signup": 2, "login": 2, "purchase": 1} and res["by_channel"] == {
        "app": 4,
        "web": 1,
    }
    assert {"from": "signup", "to": "login", "count": 2} in res["top_transitions"]
    assert res["events_per_customer"] == {"median": 2.5, "max": 3, "min": 2} and res["low_sample"] is False
    assert res["first_event"].startswith("2026-10-01") and res["last_event"].startswith("2026-10-04")


def test_to_events_skips_unusable_rows_and_keeps_metadata_objects_only():
    events = to_events(
        [
            ev("A", "x", "bad-date"),
            {"customer_id": "", "event_type": "x", "event_timestamp": "2026-10-01"},
            {**ev("A", "x", "2026-10-01T00:00:00Z"), "metadata": {"k": 1}},
            {**ev("A", "y", "2026-10-02T00:00:00Z"), "metadata": "not-a-dict"},
        ]
    )
    assert len(events) == 2 and events[0].metadata == {"k": 1} and events[1].metadata is None
    assert isinstance(events[0], JourneyEvent)


def test_tenure_groups_cannot_be_turned_into_journeys():
    """There is deliberately no function that accepts lifecycle groups as events."""
    from trichurn_experience import journey, lifecycle

    assert not hasattr(journey, "from_lifecycle") and not hasattr(lifecycle, "to_events")
    assert parse_config({}).journey_min_events >= 1
