from __future__ import annotations

from app.schemas.business import BusinessResponse
from app.schemas.common import CustomerRequest
from app.services.adapters.interface import BusinessResult, ExplanationResult
from app.services.base import BaseService, customer_payload
from app.services.mappers import to_business


class BusinessService(BaseService):
    def run(self, request: CustomerRequest, churn_probability: float | None = None,
            explanation: ExplanationResult | None = None) -> BusinessResult:
        return self.guard(self._adapter.business, customer_payload(request), churn_probability, explanation)

    def business(self, request: CustomerRequest) -> BusinessResponse:
        return to_business(request.customer_id, self.run(request))
