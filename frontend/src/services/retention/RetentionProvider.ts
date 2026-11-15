import type {
  ActionsResponse,
  AssignmentReport,
  Campaign,
  CampaignAnalytics,
  CampaignCreateInput,
  CampaignGroup,
  CampaignMetrics,
  ExecutiveSummary,
  OutcomeInput,
  OutcomeReport,
  PriorityPage,
  PriorityQuery,
  Recommendation,
  ScenarioInput,
  SimulationResult,
  UpliftReadiness,
} from '../../types/retention';

/** Everything the Retention Intelligence UI needs from a backend. The real implementation is HTTP (Phase 9 API). */
export interface RetentionProvider {
  readonly name: string;
  getSummary(): Promise<ExecutiveSummary>;
  getPriorities(query: PriorityQuery): Promise<PriorityPage>;
  getRecommendation(customerId: string): Promise<Recommendation>;
  getActions(): Promise<ActionsResponse>;
  simulate(scenarios: ScenarioInput[]): Promise<SimulationResult>;
  listCampaigns(): Promise<Campaign[]>;
  getCampaign(campaignId: string): Promise<CampaignMetrics>;
  createCampaign(input: CampaignCreateInput): Promise<Campaign>;
  assignCustomers(campaignId: string, customerIds: string[], group: CampaignGroup): Promise<AssignmentReport>;
  recordOutcomes(campaignId: string, outcomes: OutcomeInput[]): Promise<OutcomeReport>;
  getAnalytics(): Promise<CampaignAnalytics>;
  getUpliftReadiness(): Promise<UpliftReadiness>;
}
