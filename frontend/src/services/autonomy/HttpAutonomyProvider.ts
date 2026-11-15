import axios, { type AxiosInstance } from 'axios';
import type {
  AuditEvent,
  AuditQuery,
  AutonomyRecommendation,
  AutonomySummary,
  FeedbackInput,
  FeedbackRecord,
  GenerateResult,
  LearningReport,
  PagedResult,
  RecommendationQuery,
  RiskEvent,
  RiskQuery,
  ScanResult,
  WorkflowAction,
} from '../../types/autonomy';
import { toApiError } from '../retention/HttpRetentionProvider';
import type { AutonomyProvider } from './AutonomyProvider';

export const AUTONOMY_PREFIX = '/api/v1/autonomous-retention';

/** A fresh random key per user action; the server replays instead of repeating when a request is retried. */
export function newIdempotencyKey(): string {
  const random =
    typeof crypto !== 'undefined' && typeof crypto.randomUUID === 'function'
      ? crypto.randomUUID()
      : `${Date.now()}-${Math.random().toString(36).slice(2)}`;
  return `ui-${random}`;
}

export class HttpAutonomyProvider implements AutonomyProvider {
  readonly name = 'HttpAutonomyProvider';
  private readonly http: AxiosInstance;

  constructor(options: { baseUrl: string; timeoutMs?: number }) {
    this.http = axios.create({
      baseURL: options.baseUrl,
      timeout: options.timeoutMs ?? 60000,
      headers: { 'Content-Type': 'application/json' },
    });
  }

  private async get<T>(path: string, params?: Record<string, unknown>): Promise<T> {
    try {
      return (await this.http.get<T>(`${AUTONOMY_PREFIX}${path}`, { params })).data;
    } catch (error) {
      throw toApiError(error);
    }
  }

  private async post<T>(path: string, body: unknown, idempotencyKey?: string): Promise<T> {
    try {
      const headers = idempotencyKey ? { 'Idempotency-Key': idempotencyKey } : undefined;
      return (await this.http.post<T>(`${AUTONOMY_PREFIX}${path}`, body, { headers })).data;
    } catch (error) {
      throw toApiError(error);
    }
  }

  getSummary(): Promise<AutonomySummary> {
    return this.get('/summary');
  }

  getRisks(q: RiskQuery): Promise<PagedResult<RiskEvent>> {
    return this.get('/risks', { page: q.page, page_size: q.pageSize, risk_level: q.riskLevel, status: q.status });
  }

  scanRisks(): Promise<ScanResult> {
    return this.post('/risks/scan', undefined);
  }

  getRecommendations(q: RecommendationQuery): Promise<PagedResult<AutonomyRecommendation>> {
    return this.get('/recommendations', {
      page: q.page,
      page_size: q.pageSize,
      status: q.status,
      category: q.category,
      priority: q.priority,
      risk_band: q.riskBand,
    });
  }

  generateRecommendations(limit?: number): Promise<GenerateResult> {
    return this.post('/recommendations/generate', { limit });
  }

  async transition(id: string, action: WorkflowAction, note: string | undefined, key: string): Promise<AutonomyRecommendation> {
    const result = await this.post<{ recommendation: AutonomyRecommendation }>(
      `/approvals/${encodeURIComponent(id)}/${action}`,
      { note: note || undefined },
      key,
    );
    return result.recommendation;
  }

  getFeedback(page: number, pageSize?: number): Promise<PagedResult<FeedbackRecord>> {
    return this.get('/feedback', { page, page_size: pageSize });
  }

  async recordFeedback(input: FeedbackInput, key: string): Promise<FeedbackRecord> {
    const result = await this.post<{ feedback: FeedbackRecord }>(
      '/feedback',
      {
        recommendation_id: input.recommendationId,
        outcome: input.outcome,
        outcome_at: input.outcomeAt,
        data_source: input.dataSource,
        campaign_id: input.campaignId || undefined,
      },
      key,
    );
    return result.feedback;
  }

  getLearning(): Promise<LearningReport> {
    return this.get('/learning');
  }

  getAudit(q: AuditQuery): Promise<PagedResult<AuditEvent>> {
    return this.get('/audit', {
      page: q.page,
      page_size: q.pageSize,
      event_type: q.eventType,
      recommendation_id: q.recommendationId,
    });
  }
}
