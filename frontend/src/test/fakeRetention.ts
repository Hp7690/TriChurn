import type { RetentionProvider } from '../services/retention/RetentionProvider';
import { ApiError, NotFoundError } from '../services/api/errors';
import type {
  ActionOption,
  Campaign,
  CampaignAnalytics,
  CampaignMetrics,
  CustomerSnapshot,
  ExecutiveSummary,
  PriorityItem,
  PriorityPage,
  PriorityQuery,
  Recommendation,
  ScenarioInput,
  ScenarioResult,
  UpliftReadiness,
} from '../types/retention';

/**
 * TEST DOUBLE ONLY (never imported by application code). The portfolio is a tiny fixed fixture; campaign state starts
 * EMPTY, like the real database, and only contains what a test itself records.
 */
export const ACTIONS: ActionOption[] = [
  { action_id: 'discount_offer', name: 'Discount offer', cost: 400, success_rate: 0.25, eligible: true, ineligible_reason: null, expected_benefit: 0, expected_net_benefit: 0 },
  { action_id: 'loyalty_offer', name: 'Loyalty offer', cost: 300, success_rate: 0.2, eligible: true, ineligible_reason: null, expected_benefit: 0, expected_net_benefit: 0 },
];

function customer(id: string, p: number, clv: number, decision: 'INTERVENE' | 'DO_NOT_INTERVENE'): CustomerSnapshot {
  return {
    customer_id: id, churn_probability: p, risk_band: p > 0.7 ? 'CRITICAL' : 'HIGH', segment_id: 0,
    segment_name: 'Low Value / High Risk', clv, value_at_risk: Math.round(clv * p),
    decision, recommended_action_id: decision === 'INTERVENE' ? 'discount_offer' : 'no_action',
    recommended_action: decision === 'INTERVENE' ? 'Discount offer' : 'No action', action_cost: 400, action_success_rate: 0.25,
    expected_net_benefit: decision === 'INTERVENE' ? 900 : 0,
  };
}

export const PRIORITIES: PriorityItem[] = [
  { rank: 1, score: 97.2, tier: 'P1', customer: customer('C-001', 0.9, 20000, 'INTERVENE'), value_at_risk_percentile: 0.99, churn_probability_percentile: 0.98, expected_net_benefit_percentile: 0.97, reasons: ['Value at risk is higher than 99% of customers.'] },
  { rank: 2, score: 85.0, tier: 'P3', customer: customer('C-002', 0.6, 9000, 'INTERVENE'), value_at_risk_percentile: 0.9, churn_probability_percentile: 0.8, expected_net_benefit_percentile: 0.8, reasons: ['Churn probability 60.0% (HIGH risk band).'] },
  { rank: 3, score: 20.1, tier: 'MONITOR', customer: customer('C-003', 0.1, 3000, 'DO_NOT_INTERVENE'), value_at_risk_percentile: 0.2, churn_probability_percentile: 0.1, expected_net_benefit_percentile: 0.1, reasons: ['Phase 4: do not intervene.'] },
];

export const SUMMARY: ExecutiveSummary = {
  kind: 'estimate', currency_code: 'INR', currency_symbol: '₹', total_customers: 3, average_churn_probability: 0.53,
  revenue_at_risk: 20000, intervention_candidates: 2, high_priority_customers: 1, high_priority_value_at_risk: 18000,
  by_risk_band: [
    { risk_band: 'LOW', customers: 0, value_at_risk: 0, total_clv: 0 },
    { risk_band: 'HIGH', customers: 2, value_at_risk: 19000, total_clv: 29000 },
    { risk_band: 'CRITICAL', customers: 1, value_at_risk: 1000, total_clv: 3000 },
  ],
  by_segment: [{ segment_id: 0, segment_name: 'Low Value / High Risk', customers: 3, value_at_risk: 20000, intervention_candidates: 2, average_churn_probability: 0.53 }],
  recommended_campaigns: [{ action_id: 'discount_offer', action_name: 'Discount offer', customers: 2, cost_per_customer: 400, assumed_success_rate: 0.25, estimated_total_cost: 800, estimated_retained_revenue: 4750, estimated_net_benefit: 3950, estimated_roi: 4.9375 }],
  estimated_total_cost: 800, estimated_retained_revenue: 4750, estimated_net_benefit: 3950, estimated_roi: 4.9375,
  top_priorities: PRIORITIES.slice(0, 2), model_version: '2.0.0', segmentation_version: '5.0.0', dataset_sha256: 'a'.repeat(64),
  scored_at: '2025-01-01T00:00:00+00:00', note: 'Estimates only.', score_note: 'The priority score is a heuristic, not a probability.',
};

const READINESS: UpliftReadiness = {
  ready: false, status: 'NOT_READY', dataset_treatment_columns: [], treatment_assignments: 0, control_assignments: 0,
  unspecified_assignments: 0, outcomes_recorded: 0,
  checks: [{ code: 'treatment_group_size', passed: false, detail: '0 treatment assignments recorded (minimum 500).' }],
  requirements: ['A treatment indicator and a control group.'], note: 'No uplift model exists and none is claimed.',
};

export class FakeRetentionProvider implements RetentionProvider {
  readonly name = 'FakeRetentionProvider';
  calls: string[] = [];
  lastPriorityQuery: PriorityQuery | null = null;
  lastScenarios: ScenarioInput[] = [];
  failWith: Error | null = null;
  summary: ExecutiveSummary = SUMMARY;
  campaigns: Campaign[] = [];

  private guard(call: string): void {
    this.calls.push(call);
    if (this.failWith) throw this.failWith;
  }

  async getSummary() { this.guard('summary'); return this.summary; }

  async getPriorities(query: PriorityQuery): Promise<PriorityPage> {
    this.guard('priorities');
    this.lastPriorityQuery = query;
    const items = PRIORITIES.filter((p) => !query.tier || p.tier === query.tier);
    return { items, total: items.length, page: 1, page_size: query.pageSize ?? 25, page_count: 1, score_note: SUMMARY.score_note };
  }

  async getRecommendation(customerId: string): Promise<Recommendation> {
    this.guard('recommendation');
    const found = PRIORITIES.find((p) => p.customer.customer_id === customerId);
    if (!found) throw new NotFoundError('Customer not found in the scored portfolio.');
    return {
      customer_id: customerId, decision: found.customer.decision, primary_action: found.customer.decision === 'INTERVENE' ? { ...ACTIONS[0], expected_benefit: 1300, expected_net_benefit: 900 } : null,
      alternatives: [{ ...ACTIONS[1], expected_benefit: 1000, expected_net_benefit: 700 }], reasons: ['Phase 4 says intervene because expected net benefit is positive.'],
      segment_peer_note: '2 of 2 intervention candidates in the segment receive Discount offer.',
      drivers: customerId === 'C-001' ? [{ feature: 'Contract', raw_value: 'Month-to-month', shap_value: 0.41, direction: 'increases_churn' }] : [],
      explainability_available: customerId === 'C-001', priority_rank: found.rank, priority_score: found.score, priority_tier: found.tier,
      basis: 'phase4_expected_net_benefit_heuristic', causal_claim: false, uplift_available: false, note: 'Estimates only.',
      explainability_note: 'SHAP values describe the model, not causes.',
    };
  }

  async getActions() { this.guard('actions'); return { currency_code: 'INR', currency_symbol: '₹', actions: ACTIONS, source: 'configs/business.yaml' }; }

  async simulate(scenarios: ScenarioInput[]) {
    this.guard('simulate');
    this.lastScenarios = scenarios;
    const results: ScenarioResult[] = scenarios.map((s, i) => ({
      name: s.name ?? `Scenario ${i + 1}`, action_id: s.actionId, action_name: s.actionId === 'discount_offer' ? 'Discount offer' : 'Loyalty offer',
      cost_per_customer: s.costOverride ?? 400, cost_source: s.costOverride === undefined ? 'phase4_config' : 'scenario_override',
      success_rate: s.successRateOverride ?? 0.25, success_rate_source: s.successRateOverride === undefined ? 'phase4_config' : 'scenario_override',
      targeted_customers: 2, eligible_customers: 2, excluded_ineligible: 0, total_value_at_risk: 19000, total_cost: 800 + i * 100,
      estimated_retained_revenue: 4750, estimated_net_benefit: 3950 - i * 100, estimated_roi: 4.9, expected_retained_customers: 0.4,
      cost_per_expected_retained_customer: 2000, label: 'ESTIMATE', note: 'Estimates only.',
    }));
    return { results, best_by_net_benefit_index: 0, best_by_roi_index: 0, label: 'ESTIMATE' as const, note: 'Estimates only.' };
  }

  async listCampaigns() { this.guard('campaigns'); return this.campaigns; }
  async getCampaign(id: string): Promise<CampaignMetrics> { this.guard('campaign'); throw new NotFoundError(`Campaign ${id} not found.`); }

  async createCampaign(input: { name: string; actionId: string; campaignDate: string; randomized: boolean }) {
    this.guard('createCampaign');
    const c: Campaign = { campaign_id: 'cmp_test0001', name: input.name, action_id: input.actionId, campaign_date: input.campaignDate, randomized: input.randomized, notes: null, created_at: 'now' };
    this.campaigns.push(c);
    return c;
  }

  async assignCustomers(campaignId: string, customerIds: string[]) {
    this.guard('assign');
    return { campaign_id: campaignId, requested: customerIds.length, assigned: customerIds.length, unknown_customer_ids: [], ineligible_customer_ids: [], already_assigned_ids: [] };
  }

  async recordOutcomes(campaignId: string) {
    this.guard('outcomes');
    return { campaign_id: campaignId, requested: 1, recorded: 1, not_assigned_ids: [], already_recorded_ids: [] };
  }

  async getAnalytics(): Promise<CampaignAnalytics> {
    this.guard('analytics');
    return {
      campaigns: this.campaigns.map((c) => ({
        campaign_id: c.campaign_id, name: c.name, action_id: c.action_id, campaign_date: c.campaign_date, randomized: c.randomized, assigned: 0,
        outcomes_recorded: 0, outcome_coverage: null, retained: 0, churned: 0, no_response: 0, observed_retention_rate: null, estimated_cost: 0,
        estimated_benefit: 0, actual_cost: null, actual_retained_revenue: null, actual_net_benefit: null, actual_roi: null, note: 'Observed only.',
      })),
      total_assigned: 0, total_outcomes_recorded: 0, total_estimated_cost: 0, total_estimated_benefit: 0, total_actual_cost: null,
      total_actual_retained_revenue: null, note: 'Observed only; no uplift is claimed.',
    };
  }

  async getUpliftReadiness() { this.guard('readiness'); return READINESS; }
}

export const apiDown = () => new ApiError('The retention API could not be reached.', undefined);
