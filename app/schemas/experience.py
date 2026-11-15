"""Pydantic schemas for the Phase 13 experience API."""

from __future__ import annotations

from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field

from trichurn_experience.schemas import ModuleStatus

FileFormat = Literal["csv", "json"]


# ------------------------------------------------------------------------------------------------ requests
class ValidationRequest(BaseModel):
    """File content is sent as text in the JSON body and validated in memory only. Nothing is stored."""

    model_config = ConfigDict(extra="forbid", strict=True)

    format: FileFormat
    content: str = Field(..., description="The file content (CSV text or JSON text).")


class SurveyValidationRequest(ValidationRequest):
    survey_type: Literal["nps", "csat"]


class DataQualityRequest(ValidationRequest):
    dataset: Literal["feedback", "tickets", "nps", "csat", "events"]


# ------------------------------------------------------------------------------------------------ validation
class ValidationIssueModel(BaseModel):
    code: str
    severity: Literal["error", "warning"]
    message: str
    column: str | None = None
    row: int | None = None


class ValidationReportModel(BaseModel):
    kind: str
    file_format: str
    valid: bool
    rows_total: int
    rows_valid: int
    error_count: int
    warning_count: int
    columns_found: list[str]
    missing_required_columns: list[str]
    unexpected_columns: list[str]
    issues: list[ValidationIssueModel]
    issue_counts: dict[str, int]
    missing_value_counts: dict[str, int]
    duplicate_records: int
    invalid_customer_ids: int
    invalid_timestamps: int
    out_of_order_records: int
    unknown_customer_ids: int
    issues_truncated: bool
    persisted: Literal[False] = False


class ValidationResponse(BaseModel):
    report: ValidationReportModel
    generated_at: str


class DataQualityResponse(BaseModel):
    report: ValidationReportModel
    quality: dict[str, Any]
    generated_at: str


# ------------------------------------------------------------------------------------------------ module status
class ModuleRequirements(BaseModel):
    needs: list[str]
    note: str
    dataset_kind: str | None = None
    required_columns: list[str] = []
    optional_columns: list[str] = []


class ValidationSummary(BaseModel):
    rows_total: int
    rows_valid: int
    error_count: int
    warning_count: int
    valid: bool


class ModuleStatusResponse(BaseModel):
    module: str
    title: str
    status: ModuleStatus
    reason: str | None = None
    dataset_configured: bool
    requirements: ModuleRequirements
    validation: ValidationSummary | None = None
    metrics: dict[str, Any] | None = None
    generated_at: str


# ------------------------------------------------------------------------------------------------ lifecycle
class LifecycleChurn(BaseModel):
    known_labels: int
    churned: int
    churn_rate_pct: float | None
    rate_withheld_reason: str | None = None


class LifecycleGroupModel(BaseModel):
    name: str
    min_months: int
    max_months: int | None
    customers: int
    share_pct: float | None
    churn: LifecycleChurn | None
    contract_distribution: dict[str, int] | None
    monthly_charges: dict[str, float | int | None] | None
    total_charges: dict[str, float | int | None] | None
    risk: dict[str, Any] | None


class LifecycleResponse(BaseModel):
    status: ModuleStatus
    label: Literal["TENURE_PROXY"]
    is_event_based: Literal[False]
    reason: str | None
    methodology: str
    thresholds: list[dict[str, Any]]
    customers_total: int
    customers_analysed: int
    excluded: dict[str, int]
    columns_used: list[str]
    columns_missing: list[str]
    groups: list[LifecycleGroupModel]
    overall: dict[str, Any] | None
    risk_distribution: dict[str, Any] | None
    assumptions: list[str]
    limitations: list[str]
    source: str
    generated_at: str


# ------------------------------------------------------------------------------------------------ availability
class DataQualityBlock(BaseModel):
    datasets: dict[str, ValidationSummary | None]
    customer_dataset: dict[str, Any] | None


class AvailabilityResponse(BaseModel):
    enabled: bool
    config_error: str | None = None
    summary: dict[str, int]
    modules: list[ModuleStatusResponse]
    lifecycle_summary: dict[str, Any] | None
    data_quality: DataQualityBlock
    notices: list[str]
    generated_at: str
