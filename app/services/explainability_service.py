from __future__ import annotations

from app.schemas.common import CustomerRequest, ExplainRequest
from app.schemas.explainability import ExplainResponse
from app.services.adapters.interface import ExplanationResult
from app.services.base import BaseService, customer_payload
from app.services.mappers import to_explanation


class ExplainabilityService(BaseService):
    def run(self, request: CustomerRequest) -> ExplanationResult:
        return self.guard(self._adapter.explain, customer_payload(request))

    def explain(self, request: ExplainRequest) -> ExplainResponse:
        return to_explanation(request.customer_id, self.run(request), request.top_n)
