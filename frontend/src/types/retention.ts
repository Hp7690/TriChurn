/**
 * Phase 9 - Retention Intelligence types. They mirror the backend schemas in `app/schemas/retention.py`.
 * Figures marked "estimate" are computed from ASSUMED action costs/success rates (Phase 4 configuration) and are not
 * measured campaign results. Campaign "actual" fields only ever contain what users recorded.
 */

export type Decision = 'INTERVENE' | 'DO_NOT_INTERVENE';
export type PriorityTier = 'P1' | 'P2' | 'P3' | 'P4' | 'MONITOR';
export type CampaignGroup = 'treatment' | 'control' | 'unspecified';
export type CampaignOutcome = 'retained' | 'churned' | 'no_response';
export type PrioritySortField =
  | 'rank'
  | 'priority_score'
  | 'churn_probability'
  | 'value_at_risk'
  | 'clv'
  | 'expected_net_benefit';

export interface ActionOption {
  action_id: string;
  name: string;
  cost: number;
  success_rate: number;
  eligible: boolean;
  ineligible_reason: string | null;
  expected_benefit: number;
  expected_net_benefit: number;
}

export interface CustomerSnapshot {
  customer_id: string;
  churn_probability: number;
  risk_band: string;
  segment_id: number;
  segment_name: string;
  clv: number;
  value_at_risk: number;
  decision: Decision;
  recommended_action_id: string;
  recommended_action: string;
  action_cost: number;
  action_success_rate: number;
  expected_net_benefit: number;
}

export interface PriorityItem {
  rank: number;
  score: number;
  tier: PriorityTier;
  customer: CustomerSnapshot;
  value_at_risk_percentile: number;
  churn_probability_percentile: number;
  expected_net_benefit_percentile: number;
  reasons: string[];
}

export interface RiskBandSummary {
  risk_band: string;
  customers: number;
  value_at_risk: number;
  total_clv: number;
}

export interface SegmentSummary {
  segment_id: number;
  segment_name: string;
  customers: number;
  value_at_risk: number;
  intervention_candidates: number;
  average_churn_probability: number;
}

export interface CampaignEstimate {
  action_id: string;
  action_name: string;
  customers: number;
  cost_per_customer: number;
  assumed_success_rate: number;
  estimated_total_cost: number;
  estimated_retained_revenue: number;
  estimated_net_benefit: number;
  estimated_roi: number | null;
}

export interface ExecutiveSummary {
  kind: 'estimate';
  currency_code: string;
  currency_symbol: string;
  total_customers: number;
  average_churn_probability: number;
  revenue_at_risk: number;
  intervention_candidates: number;
  high_priority_customers: number;
  high_priority_value_at_risk: number;
  by_risk_band: RiskBandSummary[];
  by_segment: SegmentSummary[];
  recommended_campaigns: CampaignEstimate[];
  estimated_total_cost: number;
  estimated_retained_revenue: number;
  estimated_net_benefit: number;
  estimated_roi: number | null;
  top_priorities: PriorityItem[];
  model_version: string;
  segmentation_version: string;
  dataset_sha256: string;
  scored_at: string;
  note: string;
  score_note: string;
}

export interface PriorityQuery {
  page?: number;
  pageSize?: number;
  search?: string;
  riskBand?: string;
  segmentId?: number;
  decision?: Decision;
  tier?: PriorityTier;
  minChurnProbability?: number;
  sortBy?: PrioritySortField;
  descending?: boolean;
}

export interface PriorityPage {
  items: PriorityItem[];
  total: number;
  page: number;
  page_size: number;
  page_count: number;
  score_note: string;
}

export interface Driver {
  feature: string;
  raw_value: string | number | boolean | null;
  shap_value: number;
  direction: string;
}

export interface Recommendation {
  customer_id: string;
  decision: Decision;
  primary_action: ActionOption | null;
  alternatives: ActionOption[];
  reasons: string[];
  segment_peer_note: string;
  drivers: Driver[];
  explainability_available: boolean;
  priority_rank: number;
  priority_score: number;
  priority_tier: PriorityTier;
  basis: string;
  causal_claim: boolean;
  uplift_available: boolean;
  note: string;
  explainability_note: string;
}

export interface ActionsResponse {
  currency_code: string;
  currency_symbol: string;
  actions: ActionOption[];
  source: string;
}

export interface ScenarioInput {
  name?: string;
  actionId: string;
  costOverride?: number;
  successRateOverride?: number;
  decisionFilter: 'intervene' | 'any';
  riskBands: string[];
  topN?: number;
}

export interface ScenarioResult {
  name: string;
  action_id: string;
  action_name: string;
  cost_per_customer: number;
  cost_source: 'phase4_config' | 'scenario_override';
  success_rate: number;
  success_rate_source: 'phase4_config' | 'scenario_override';
  targeted_customers: number;
  eligible_customers: number;
  excluded_ineligible: number;
  total_value_at_risk: number;
  total_cost: number;
  estimated_retained_revenue: number;
  estimated_net_benefit: number;
  estimated_roi: number | null;
  expected_retained_customers: number;
  cost_per_expected_retained_customer: number | null;
  label: 'ESTIMATE';
  note: string;
}

export interface SimulationResult {
  results: ScenarioResult[];
  best_by_net_benefit_index: number | null;
  best_by_roi_index: number | null;
  label: 'ESTIMATE';
  note: string;
}

export interface Campaign {
  campaign_id: string;
  name: string;
  action_id: string;
  campaign_date: string;
  randomized: boolean;
  notes: string | null;
  created_at: string;
}

export interface CampaignCreateInput {
  name: string;
  actionId: string;
  campaignDate: string;
  randomized: boolean;
  notes?: string;
}

export interface AssignmentReport {
  campaign_id: string;
  requested: number;
  assigned: number;
  unknown_customer_ids: string[];
  ineligible_customer_ids: string[];
  already_assigned_ids: string[];
}

export interface OutcomeInput {
  customerId: string;
  outcome: CampaignOutcome;
  actualCost?: number;
  actualRetainedRevenue?: number;
}

export interface OutcomeReport {
  campaign_id: string;
  requested: number;
  recorded: number;
  not_assigned_ids: string[];
  already_recorded_ids: string[];
}

export interface CampaignMetrics {
  campaign_id: string;
  name: string;
  action_id: string;
  campaign_date: string;
  randomized: boolean;
  assigned: number;
  outcomes_recorded: number;
  outcome_coverage: number | null;
  retained: number;
  churned: number;
  no_response: number;
  observed_retention_rate: number | null;
  estimated_cost: number;
  estimated_benefit: number;
  actual_cost: number | null;
  actual_retained_revenue: number | null;
  actual_net_benefit: number | null;
  actual_roi: number | null;
  note: string;
}

export interface CampaignAnalytics {
  campaigns: CampaignMetrics[];
  total_assigned: number;
  total_outcomes_recorded: number;
  total_estimated_cost: number;
  total_estimated_benefit: number;
  total_actual_cost: number | null;
  total_actual_retained_revenue: number | null;
  note: string;
}

export interface ReadinessCheck {
  code: string;
  passed: boolean;
  detail: string;
}

export interface UpliftReadiness {
  ready: boolean;
  status: string;
  dataset_treatment_columns: string[];
  treatment_assignments: number;
  control_assignments: number;
  unspecified_assignments: number;
  outcomes_recorded: number;
  checks: ReadinessCheck[];
  requirements: string[];
  note: string;
}
