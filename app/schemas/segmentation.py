"""Phase 5 segment assignment response (nearest centroid of the LOCKED artifact; nothing is fitted per request)."""
from __future__ import annotations

from pydantic import BaseModel, Field


class SegmentResponse(BaseModel):
    customer_id: str | None
    segment_id: int
    segment_name: str
    distance_to_centroid: float = Field(
        ge=0.0, description="Euclidean clustering distance in the scaled feature space. NOT a probability.")
    segment_model_version: str
    segment_count: int = Field(description="Number of segments (K) of the locked artifact.")
    segment_customer_count: int | None = Field(description="Segment size in the TRAIN population (artifact catalog).")
    segment_priority_rank: int | None
    segment_priority_tier: str | None
    note: str
