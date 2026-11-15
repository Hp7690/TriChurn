/** Phase 11 types; they mirror `app/schemas/autonomy.py`. Estimated and observed figures are always separate fields. */

export type WorkflowStatus = 'pending' | 'approved' | 'rejected' | 'executed' | 'failed' | 'cancelled';
export type WorkflowAction = 'approve' | 'reject' | 'cancel' | 'execute' | 'fail';
export type FeedbackOutcome = 'retained' | 'churned' | 'no_response';

export interface AutonomyStatus {
  agent_enabled: boolean;
  monitoring_enabled: boolean;
  monitoring_mode: string;
  approvals_enabled_in_config: boolean;
  identity_provider_configured: boolean;
  approvals_available: boolean;
  execution_integration: string;
  learning_enabled: boolean;
  rules_version: string;
}

export interface AutonomySummary {
  status: AutonomyStatus;
  recommendations: { status: Record<string, number>; category: Record<string, number>; priority: Record<string, number> };
  open_risk_events: Record<string, number>;
  latest_snapshot: { snapshot_id: number; created_at: string; customer_count: number } | null;
  estimated: {
    pending_recommendations_with_phase4_estimate: number;
    estimated_net_benefit_pending: number;
    is_estimate: true;
    note: string;
  };
  observed: { validated_outcomes: number };
  store: Record<string, number>;
}

export interface PagedResult<T> {
  items: T[];
  total: number;
  page: number;
  page_size: number;
  page_count: number;
}

export interface AutonomyRecommendation {
  recommendation_id: string;
  customer_id: string;
  category: string;
  action_id: string | null;
  action_name: string | null;
  reason: string;
  risk_band: string;
  churn_probability: number;
  priority: string;
  source: string;
  rule_id: string;
  rules_version: string;
  confidence: number | null;
  evidence: Record<string, unknown>;
  status: WorkflowStatus;
  created_at: string;
  updated_at: string;
}

export interface RiskEvent {
  event_id: string;
  customer_id: string;
  event_type: string;
  from_band: string | null;
  to_band: string;
  probability_before: number | null;
  probability_after: number;
  detected_at: string;
  snapshot_id: number;
  source: string;
  status: 'new' | 'resolved';
}

export interface ScanResult {
  status: 'baseline' | 'unchanged' | 'compared';
  snapshot_id: number;
  previous_snapshot_id: number | null;
  customers: number;
  events_created: number;
  events_resolved: number;
  note: string;
}

export interface GenerateResult {
  considered: number;
  created: number;
  skipped_existing: number;
  rules_version: string;
  note: string;
}

export interface AuditEvent {
  audit_id: number;
  event_type: string;
  recommendation_id: string | null;
  customer_id: string | null;
  from_status: string | null;
  to_status: string | null;
  actor: string;
  actor_authenticated: boolean;
  detail: string;
  created_at: string;
}

export interface FeedbackRecord {
  feedback_id: string;
  recommendation_id: string;
  customer_id: string;
  recommended_action: string | null;
  approval_decision: string;
  campaign_id: string | null;
  outcome: FeedbackOutcome;
  outcome_at: string;
  data_source: string;
  observed: boolean;
  recorded_by: string;
  recorded_at: string;
}

export interface LearningReport {
  validated_outcomes: number;
  by_action: Array<{ action: string; outcomes: Record<string, number>; total: number; observed_retained_share: number }>;
  observed_vs_estimated: string;
  checks: Array<{ code: string; passed: boolean; detail: string }>;
  learning_enabled: boolean;
  status: string;
  note: string;
}

export interface RecommendationQuery {
  page?: number;
  pageSize?: number;
  status?: WorkflowStatus;
  category?: string;
  priority?: string;
  riskBand?: string;
}

export interface RiskQuery {
  page?: number;
  pageSize?: number;
  riskLevel?: string;
  status?: 'new' | 'resolved';
}

export interface AuditQuery {
  page?: number;
  pageSize?: number;
  eventType?: string;
  recommendationId?: string;
}

export interface FeedbackInput {
  recommendationId: string;
  outcome: FeedbackOutcome;
  outcomeAt: string;
  dataSource: string;
  campaignId?: string;
}
