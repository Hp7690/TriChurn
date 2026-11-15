from __future__ import annotations

from tests.api.conftest import assert_error
from tests.support.fake_adapter import FakeAdapter

URL = "/api/v1/segment"


def test_segment_response(client, payload):
    r = client.post(URL, json=payload)
    assert r.status_code == 200
    b = r.json()
    assert set(b) == {"customer_id", "segment_id", "segment_name", "distance_to_centroid", "segment_model_version",
                      "segment_count", "segment_customer_count", "segment_priority_rank", "segment_priority_tier",
                      "note"}
    assert b["distance_to_centroid"] >= 0 and b["segment_count"] == 3
    assert not any("probab" in key for key in b)                          # a clustering distance is not a probability
    description = client.get("/openapi.json").json()["components"]["schemas"]["SegmentResponse"]["properties"]
    assert "NOT a probability" in description["distance_to_centroid"]["description"]


def test_segment_only_calls_the_adapters_assignment(client, adapter, payload):
    client.post(URL, json=payload)
    assert [op for op, _ in adapter.calls] == ["segment"]


def test_segment_uses_the_same_strict_validation(client, adapter, payload):
    payload["features"]["tenure"] = -3
    assert_error(client.post(URL, json=payload), 422, "INVALID_INPUT")
    assert adapter.calls == []


def test_segmentation_unavailable_is_a_clean_503(make_client, payload):
    assert_error(make_client(FakeAdapter(unavailable={"segmentation"})).post(URL, json=payload), 503,
                 "CAPABILITY_UNAVAILABLE")
