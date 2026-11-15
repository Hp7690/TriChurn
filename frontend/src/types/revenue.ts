/** Phase 12 types. Mirror app/schemas/revenue_intelligence.py (single status vocabulary shared with the API). */
export type EvidenceStatus =
  | 'ACTUAL'
  | 'ESTIMATED'
  | 'PROXY'
  | 'ILLUSTRATIVE'
  | 'UNAVAILABLE'
  | 'BLOCKED_BY_MISSING_DATA';

export interface Meta {
  calculated_at: string;
  data_source: string;
  methodology_note: string;
  package_version: string;
}
export interface PageMeta extends Meta {
  total: number;
  page: number;
  page_size: number;
  page_count: number;
}
export interface Metric {
  key: string;
  name: string;
  description: string;
  value: number | string | null;
  unit: string;
  status: EvidenceStatus;
  formula: string;
  source_fields: string[];
  assumptions: string[];
  limitations: string[];
  reason: string | null;
  calculated_at: string;
}
export interface Quality {
  rows_read: number;
  rows_used: number;
  duplicate_ids_dropped: number;
  missing_customer_id: number;
  invalid_tenure: number;
  invalid_monthly_charges: number;
  missing_total_charges: number;
  invalid_total_charges: number;
  zero_tenure_rows: number;
  inconsistent_total_vs_monthly: number;
  churn_unknown: number;
  missing_columns: string[];
  notes: string[];
}
export interface SegmentRow {
  segment: string;
  customers: number;
  customer_share: number;
  observed_billing_total: number | null;
  observed_billing_share: number | null;
  avg_observed_billing: number | null;
  avg_estimated_clv: number | null;
  monthly_recurring_total: number | null;
  churned_customers: number;
  churn_rate: number | null;
  churn_known_customers: number;
}
export interface HistBin {
  lower: number;
  upper: number;
  count: number;
}
export interface ClvSummary extends Meta {
  metrics: Metric[];
  scenario: {
    status: EvidenceStatus;
    assumptions_confirmed: boolean;
    remaining_months_by_contract: Record<string, number>;
    monthly_discount_rate: number;
    reason: string | null;
  };
  distribution_observed_billing: HistBin[];
  distribution_estimated_clv: HistBin[];
  distribution_status: EvidenceStatus;
  distribution_observed_billing_status: EvidenceStatus;
  distribution_estimated_clv_status: EvidenceStatus;
  customers_without_valid_billing: number;
  customers_with_inconsistent_billing: number;
  data_quality: Quality;
}
export interface ClvCustomer {
  customer_id: string;
  contract: string | null;
  tenure_months: number | null;
  monthly_charges: number | null;
  observed_billing: number | null;
  observed_billing_status: EvidenceStatus;
  estimated_forward_value: number | null;
  estimated_clv: number | null;
  estimated_clv_status: EvidenceStatus;
  value_segment: string;
  churned: boolean | null;
  billing_inconsistent: boolean;
}
export interface Paged<T> extends PageMeta {
  items: T[];
}
export interface ClvSegments extends Meta {
  metric: string;
  method: string;
  metric_status: EvidenceStatus;
  reason: string | null;
  thresholds: number[] | null;
  labels: string[];
  note: string;
  segments: SegmentRow[];
}
export interface RiskGroupRow {
  group: string;
  customers: number;
  active_customers: number;
  flagged_customers: number;
  flagged_share_of_active: number | null;
  flagged_monthly_exposure: number | null;
  flagged_billing_exposure: number | null;
  expected_monthly_exposure: number | null;
  churned_monthly_context: number | null;
}
export interface RiskSummary extends Meta {
  metrics: Metric[];
  flagged_customers: number;
  active_customers: number;
  probability_weighting: { available: boolean; reason: string; provenance: string };
  rule_definition: {
    indicators: Record<string, unknown>;
    min_indicators_to_flag: number;
    status: EvidenceStatus;
    is_probability: boolean;
  };
  by_contract: RiskGroupRow[];
  by_tenure_group: RiskGroupRow[];
  by_value_segment: RiskGroupRow[];
  warnings: string[];
}
export interface RiskCustomer {
  customer_id: string;
  contract: string | null;
  tenure_months: number | null;
  tenure_group: string;
  value_segment: string;
  monthly_charges: number | null;
  observed_billing: number | null;
  indicators: string[];
  indicator_count: number;
  exposure_basis: string;
  exposure_status: EvidenceStatus;
  churn_probability: number | null;
  expected_monthly_exposure: number | null;
}
export interface OpportunitiesSummary extends Meta {
  metrics: Metric[];
  customers_with_opportunity: number;
  total_recommendations: number;
  eligible_recommendations: number;
  by_type: Record<string, number>;
  by_target: Record<string, number>;
  by_value_segment: Record<string, number>;
  by_eligibility: Record<string, number>;
  by_data_confidence: Record<string, number>;
  requires_human_review: boolean;
  warnings: string[];
}
export interface Opportunity {
  customer_id: string;
  recommendation_type: string;
  suggested_category: string;
  reason: string;
  evidence_fields: Record<string, unknown>;
  eligibility: string;
  data_confidence: string;
  missing_evidence: string[];
  value_segment: string | null;
  status: string;
  requires_human_review: boolean;
  caution: string | null;
  quantified_uplift: null;
}
export interface CohortRow {
  cohort: string;
  customers: number;
  customer_share: number;
  churned_customers: number;
  churn_rate: number | null;
  avg_monthly_charges: number | null;
  avg_observed_billing: number | null;
  avg_estimated_clv: number | null;
  monthly_recurring_total: number | null;
  observed_billing_total: number | null;
}
export interface CohortTenure extends Meta {
  method: string;
  status: EvidenceStatus;
  limitations: string[];
  tenure_buckets: CohortRow[];
  lifecycle_groups: CohortRow[];
  contract_cohorts: CohortRow[];
}
export interface CohortSummary extends Meta {
  method: string;
  status: EvidenceStatus;
  metrics: Metric[];
  supported_now: string[];
  blocked_by_missing_data: { analysis: string; status: EvidenceStatus; reason: string }[];
  acquisition_cohorts: { status: string; reason: string | null; cohorts: unknown[] };
  tenure_buckets: CohortRow[];
  limitations: string[];
}
export interface ForecastReadiness extends Meta {
  state: string;
  readiness: {
    state: string;
    reasons: string[];
    rows_received: number;
    rows_valid: number;
    invalid_dates: number;
    invalid_revenue: number;
    negative_revenue: number;
    duplicate_rows: number;
    distinct_customers: number;
    periods_observed: number;
    first_period: string | null;
    last_period: string | null;
    missing_periods: string[];
    missing_period_share: number | null;
    min_periods_required: number;
    seasonality_ready: boolean;
    forecast_executed: boolean;
  };
  schema: { required: Record<string, string>; optional: Record<string, string>; frequency: string };
  metrics: Metric[];
  requirements: Record<string, unknown>;
  note: string;
  backtest?: {
    status: string;
    reason?: string;
    note?: string;
    results?: { model: string; mae: number; mape: number | null }[];
  } | null;
}
export interface ForecastRowInput {
  period: string;
  customer_id: string;
  revenue: number | string | null;
  product?: string;
  segment?: string;
}
export interface Availability extends Meta {
  modules: { module: string; status: EvidenceStatus; detail: string }[];
  data_quality: Quality;
  status_legend: Record<string, string>;
  metric_definitions: {
    key: string;
    name: string;
    description: string;
    formula: string;
    source_fields: string[];
    default_status: EvidenceStatus;
    assumptions: string[];
    limitations: string[];
    unit: string;
  }[];
  independence: { requires_phase_9: boolean; requires_phase_11: boolean };
}
export interface Summary extends Meta {
  headline_metrics: Metric[];
  clv: { segments: SegmentRow[] };
  risk: { by_contract: RiskGroupRow[]; by_tenure_group: RiskGroupRow[]; flagged_customers: number };
  opportunities: { by_type: Record<string, number>; customers_with_opportunity: number };
  cohorts: CohortRow[];
  forecast_state: string;
  data_quality: Quality;
  warnings: string[];
}
export interface PageQuery {
  page?: number;
  page_size?: number;
}
export interface ClvCustomerQuery extends PageQuery {
  segment?: string;
  customer_id?: string;
  sort_by?: 'customer_id' | 'observed_billing' | 'estimated_clv' | 'monthly_charges' | 'tenure';
  descending?: boolean;
}
export interface RiskCustomerQuery extends PageQuery {
  contract?: string;
  segment?: string;
  tenure_group?: string;
}
export interface OpportunityQuery extends PageQuery {
  recommendation_type?: string;
  eligibility?: string;
  segment?: string;
  customer_id?: string;
}
