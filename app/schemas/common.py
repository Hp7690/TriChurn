"""Shared schemas: the customer request, the error envelope and the health/readiness models."""
from __future__ import annotations

from typing import Annotated, Any, Literal

from pydantic import BaseModel, ConfigDict, Field, model_validator

YesNo = Literal["Yes", "No"]
YesNoNoInternet = Literal["Yes", "No", "No internet service"]
NonNegativeFloat = Annotated[float, Field(ge=0, allow_inf_nan=False)]


class CustomerFeatures(BaseModel):
    """The 19 raw customer features the locked Phase 2 model was trained on (IBM Telco), by their dataset names.

    EVERY field is required: nothing is defaulted or imputed here. ``TotalCharges`` is required but may be ``null``
    only for a brand-new customer (``tenure == 0``), which is exactly the pattern in the training data (11 blank
    values, all with tenure 0). Categorical values must come from the dataset's known domains. Unknown fields are
    rejected, and no type coercion is applied (``"10"`` is not accepted for ``tenure``).
    """

    model_config = ConfigDict(extra="forbid", strict=True)

    SeniorCitizen: Annotated[int, Field(ge=0, le=1)]      # strict int: JSON true/false is rejected
    tenure: Annotated[int, Field(ge=0)]
    MonthlyCharges: NonNegativeFloat
    TotalCharges: NonNegativeFloat | None = Field(...)
    gender: Literal["Female", "Male"]
    Partner: YesNo
    Dependents: YesNo
    PhoneService: YesNo
    MultipleLines: Literal["Yes", "No", "No phone service"]
    InternetService: Literal["DSL", "Fiber optic", "No"]
    OnlineSecurity: YesNoNoInternet
    OnlineBackup: YesNoNoInternet
    DeviceProtection: YesNoNoInternet
    TechSupport: YesNoNoInternet
    StreamingTV: YesNoNoInternet
    StreamingMovies: YesNoNoInternet
    Contract: Literal["Month-to-month", "One year", "Two year"]
    PaperlessBilling: YesNo
    PaymentMethod: Literal["Bank transfer (automatic)", "Credit card (automatic)", "Electronic check", "Mailed check"]

    @model_validator(mode="after")
    def _total_charges_null_only_for_new_customers(self) -> CustomerFeatures:
        if self.TotalCharges is None and self.tenure != 0:
            raise ValueError("TotalCharges may be null only when tenure is 0.")
        return self


class CustomerRequest(BaseModel):
    """Body of every customer endpoint. ``customer_id`` is optional and only echoed back."""

    model_config = ConfigDict(
        extra="forbid", strict=True,
        json_schema_extra={"example": {
            "customer_id": "EXAMPLE-0001",
            "features": {
                "SeniorCitizen": 0, "tenure": 10, "MonthlyCharges": 29.75, "TotalCharges": 301.9,
                "gender": "Female", "Partner": "No", "Dependents": "No", "PhoneService": "No",
                "MultipleLines": "No phone service", "InternetService": "DSL", "OnlineSecurity": "Yes",
                "OnlineBackup": "No", "DeviceProtection": "No", "TechSupport": "No", "StreamingTV": "No",
                "StreamingMovies": "No", "Contract": "Month-to-month", "PaperlessBilling": "No",
                "PaymentMethod": "Mailed check"}}})

    customer_id: str | None = Field(default=None, min_length=1, max_length=64)
    features: CustomerFeatures


class ExplainRequest(CustomerRequest):
    """Customer plus an optional cut-off for how many source features to return (default: all)."""

    top_n: Annotated[int, Field(strict=True, ge=1, le=100)] | None = None          # strict: "3" is rejected


# ------------------------------------------------------------------------------------------------ errors
class ErrorDetail(BaseModel):
    field: str
    message: str


class ErrorBody(BaseModel):
    code: str
    message: str
    details: list[ErrorDetail] | None = None
    error_id: str | None = None


class ErrorResponse(BaseModel):
    error: ErrorBody


# ----------------------------------------------------------------------------------------------- health
class HealthResponse(BaseModel):
    status: Literal["ok"]
    service: str
    api_version: str
    app_version: str
    environment: str


class LivenessResponse(BaseModel):
    status: Literal["alive"]


class ReadinessCheck(BaseModel):
    name: str
    status: Literal["ok", "unavailable"]
    detail: str


class ReadinessResponse(BaseModel):
    ready: bool
    checks: list[ReadinessCheck]
    details: dict[str, Any] | None = None
