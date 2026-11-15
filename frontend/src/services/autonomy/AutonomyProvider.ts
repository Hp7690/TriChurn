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

/** Everything the Phase 11 UI needs from a backend. The real implementation is HTTP (Phase 11 API). */
export interface AutonomyProvider {
  readonly name: string;
  getSummary(): Promise<AutonomySummary>;
  getRisks(query: RiskQuery): Promise<PagedResult<RiskEvent>>;
  scanRisks(): Promise<ScanResult>;
  getRecommendations(query: RecommendationQuery): Promise<PagedResult<AutonomyRecommendation>>;
  generateRecommendations(limit?: number): Promise<GenerateResult>;
  /** Needs an authenticated reviewer server-side; without an identity provider the API answers 403. */
  transition(recommendationId: string, action: WorkflowAction, note: string | undefined, idempotencyKey: string): Promise<AutonomyRecommendation>;
  getFeedback(page: number, pageSize?: number): Promise<PagedResult<FeedbackRecord>>;
  recordFeedback(input: FeedbackInput, idempotencyKey: string): Promise<FeedbackRecord>;
  getLearning(): Promise<LearningReport>;
  getAudit(query: AuditQuery): Promise<PagedResult<AuditEvent>>;
}
