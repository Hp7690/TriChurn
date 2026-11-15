import axios, { type AxiosInstance } from 'axios';
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
import { ApiError, NotFoundError } from '../api/errors';
import type { RetentionProvider } from './RetentionProvider';

export const RETENTION_PREFIX = '/api/v1/retention';

export interface HttpRetentionOptions {
  baseUrl: string;
  /** The first request scores the whole portfolio on the server, so allow more time than a normal call. */
  timeoutMs?: number;
}

/** Converts the backend's uniform error envelope `{ error: { code, message } }` into the app's error types. */
export function toApiError(error: unknown): Error {
  if (axios.isAxiosError(error)) {
    const status = error.response?.status;
    const data: unknown = error.response?.data;
    const envelope = (data as { error?: { message?: unknown } } | undefined)?.error;
    const message =
      typeof envelope?.message === 'string' && envelope.message !== ''
        ? envelope.message
        : status === undefined
          ? 'The retention API could not be reached. Check that the backend is running and the API URL is correct.'
          : `The retention API returned HTTP ${status}.`;
    return status === 404 ? new NotFoundError(message) : new ApiError(message, status);
  }
  return error instanceof Error ? error : new Error('Unknown error');
}

export class HttpRetentionProvider implements RetentionProvider {
  readonly name = 'HttpRetentionProvider';
  private readonly http: AxiosInstance;

  constructor(options: HttpRetentionOptions) {
    this.http = axios.create({
      baseURL: options.baseUrl,
      timeout: options.timeoutMs ?? 60000,
      headers: { 'Content-Type': 'application/json' },
    });
  }

  private async get<T>(path: string, params?: Record<string, unknown>): Promise<T> {
    try {
      return (await this.http.get<T>(`${RETENTION_PREFIX}${path}`, { params })).data;
    } catch (error) {
      throw toApiError(error);
    }
  }

  private async post<T>(path: string, body: unknown): Promise<T> {
    try {
      return (await this.http.post<T>(`${RETENTION_PREFIX}${path}`, body)).data;
    } catch (error) {
      throw toApiError(error);
    }
  }

  getSummary(): Promise<ExecutiveSummary> {
    return this.get('/summary');
  }

  getPriorities(q: PriorityQuery): Promise<PriorityPage> {
    const params: Record<string, unknown> = {
      page: q.page,
      page_size: q.pageSize,
      search: q.search?.trim() || undefined,
      risk_band: q.riskBand,
      segment_id: q.segmentId,
      decision: q.decision,
      tier: q.tier,
      min_churn_probability: q.minChurnProbability,
      sort_by: q.sortBy,
      descending: q.descending,
    };
    return this.get('/priorities', params);
  }

  getRecommendation(customerId: string): Promise<Recommendation> {
    return this.get(`/customers/${encodeURIComponent(customerId)}/recommendation`);
  }

  getActions(): Promise<ActionsResponse> {
    return this.get('/actions');
  }

  simulate(scenarios: ScenarioInput[]): Promise<SimulationResult> {
    return this.post('/simulate', {
      scenarios: scenarios.map((s) => ({
        name: s.name || undefined,
        action_id: s.actionId,
        cost_override: s.costOverride,
        success_rate_override: s.successRateOverride,
        decision_filter: s.decisionFilter,
        risk_bands: s.riskBands,
        top_n: s.topN,
      })),
    });
  }

  async listCampaigns(): Promise<Campaign[]> {
    return (await this.get<{ campaigns: Campaign[] }>('/campaigns')).campaigns;
  }

  getCampaign(campaignId: string): Promise<CampaignMetrics> {
    return this.get(`/campaigns/${encodeURIComponent(campaignId)}`);
  }

  createCampaign(input: CampaignCreateInput): Promise<Campaign> {
    return this.post('/campaigns', {
      name: input.name,
      action_id: input.actionId,
      campaign_date: input.campaignDate,
      randomized: input.randomized,
      notes: input.notes || undefined,
    });
  }

  assignCustomers(campaignId: string, customerIds: string[], group: CampaignGroup): Promise<AssignmentReport> {
    return this.post(`/campaigns/${encodeURIComponent(campaignId)}/assignments`, { customer_ids: customerIds, group });
  }

  recordOutcomes(campaignId: string, outcomes: OutcomeInput[]): Promise<OutcomeReport> {
    return this.post(`/campaigns/${encodeURIComponent(campaignId)}/outcomes`, {
      outcomes: outcomes.map((o) => ({
        customer_id: o.customerId,
        outcome: o.outcome,
        actual_cost: o.actualCost,
        actual_retained_revenue: o.actualRetainedRevenue,
      })),
    });
  }

  getAnalytics(): Promise<CampaignAnalytics> {
    return this.get('/analytics');
  }

  getUpliftReadiness(): Promise<UpliftReadiness> {
    return this.get('/uplift-readiness');
  }
}
