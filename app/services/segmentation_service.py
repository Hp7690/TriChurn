from __future__ import annotations

from app.schemas.common import CustomerRequest
from app.schemas.segmentation import SegmentResponse
from app.services.adapters.interface import SegmentResult
from app.services.base import BaseService, customer_payload
from app.services.mappers import to_segment


class SegmentationService(BaseService):
    def run(self, request: CustomerRequest) -> SegmentResult:
        return self.guard(self._adapter.segment, customer_payload(request))

    def segment(self, request: CustomerRequest) -> SegmentResponse:
        return to_segment(request.customer_id, self.run(request))
