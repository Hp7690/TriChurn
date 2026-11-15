from __future__ import annotations

from app.schemas.common import CustomerRequest
from app.schemas.prediction import PredictionResponse
from app.services.adapters.interface import PredictionResult
from app.services.base import BaseService, customer_payload
from app.services.mappers import to_prediction


class PredictionService(BaseService):
    def run(self, request: CustomerRequest) -> PredictionResult:
        return self.guard(self._adapter.predict, customer_payload(request))

    def predict(self, request: CustomerRequest) -> PredictionResponse:
        return to_prediction(request.customer_id, self.run(request))
