/** Types for /api/v1/experience (Phase 13). They mirror app/schemas/experience.py. */

export type ModuleStatus =
  | 'AVAILABLE'
  | 'PARTIALLY_AVAILABLE'
  | 'BLOCKED_BY_MISSING_DATA'
  | 'DISABLED'
  | 'VALIDATION_FAILED';

export type ModuleKey = 'lifecycle' | 'feedback' | 'sentiment' | 'complaints' | 'nps' | 'csat' | 'journey';

export interface ModuleRequirements {
  needs: string[];
  note: string;
  dataset_kind: string | null;
  required_columns: string[];
  optional_columns: string[];
}

export interface ValidationSummary {
  rows_total: number;
  rows_valid: number;
  error_count: number;
  warning_count: number;
  valid: boolean;
}

export interface ModuleStatusInfo {
  module: ModuleKey;
  title: string;
  status: ModuleStatus;
  reason: string | null;
  dataset_configured: boolean;
  requirements: ModuleRequirements;
  validation: ValidationSummary | null;
  metrics: Record<string, unknown> | null;
  generated_at: string;
}

export interface LifecycleSummaryGroup {
  name: string;
  customers: number;
  share_pct: number | null;
}

export interface CustomerDatasetQuality {
  source: string;
  rows: number;
  columns: number;
  duplicate_customer_ids: number | null;
  missing_tenure_or_invalid: number | null;
  missing_total_charges: number | null;
  missing_monthly_charges: number | null;
  missing_churn_label: number | null;
}

export interface AvailabilityResponse {
  enabled: boolean;
  config_error: string | null;
  summary: Record<ModuleStatus, number>;
  modules: ModuleStatusInfo[];
  lifecycle_summary: {
    label: 'TENURE_PROXY';
    is_event_based: false;
    customers_analysed: number;
    groups: LifecycleSummaryGroup[];
  } | null;
  data_quality: {
    datasets: Record<string, ValidationSummary | null>;
    customer_dataset: CustomerDatasetQuality | null;
  };
  notices: string[];
  generated_at: string;
}

export interface NumericSummary {
  count: number;
  mean: number | null;
  median: number | null;
  min: number | null;
  max: number | null;
  sum: number | null;
  missing?: number | null;
}

export interface LifecycleGroup {
  name: string;
  min_months: number;
  max_months: number | null;
  customers: number;
  share_pct: number | null;
  churn: {
    known_labels: number;
    churned: number;
    churn_rate_pct: number | null;
    rate_withheld_reason: string | null;
  } | null;
  contract_distribution: Record<string, number> | null;
  monthly_charges: NumericSummary | null;
  total_charges: NumericSummary | null;
  risk: { counts: Record<'LOW' | 'MEDIUM' | 'HIGH', number>; missing_probability: number } | null;
}

export interface LifecycleResponse {
  status: ModuleStatus;
  label: 'TENURE_PROXY';
  is_event_based: false;
  reason: string | null;
  methodology: string;
  thresholds: Array<{ name: string; min_months: number; max_months: number | null }>;
  customers_total: number;
  customers_analysed: number;
  excluded: { total: number; invalid_or_missing_tenure: number };
  columns_used: string[];
  columns_missing: string[];
  groups: LifecycleGroup[];
  overall: { churn_labels_known: number; churned: number; churn_rate_pct: number | null } | null;
  risk_distribution: {
    status: ModuleStatus;
    bands: Record<'LOW' | 'MEDIUM' | 'HIGH', number> | null;
    reason?: string;
    note?: string;
    missing_probability?: number;
    source?: string;
  } | null;
  assumptions: string[];
  limitations: string[];
  source: string;
  generated_at: string;
}
