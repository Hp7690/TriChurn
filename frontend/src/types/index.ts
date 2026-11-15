/**
 * TriChurn — shared frontend domain types.
 *
 * These mirror the *concepts* produced by the locked Phase 1–5 pipeline
 * (prediction, SHAP explainability, business value, segmentation). The UI
 * only ever consumes these types; where the data comes from (mock or the
 * Phase 6 FastAPI) is decided in `src/services`.
 */

export type RiskBand = 'Low' | 'Medium' | 'High';
export type ChurnLabel = 'Churn' | 'No Churn';
export type InterventionDecision = 'Intervene' | 'Do not intervene';
export type DataMode = 'mock' | 'live';

export type SegmentId = 'low-value-high-risk' | 'high-value-stable' | 'low-value-stable';

export type ContractType = 'Month-to-month' | 'One year' | 'Two year';
export type InternetService = 'DSL' | 'Fiber optic' | 'None';
export type PaymentMethod = 'Electronic check' | 'Mailed check' | 'Bank transfer' | 'Credit card';

export interface Customer {
  customerId: string;
  /** Months with the company (Phase 5 clustering feature `tenure`). */
  tenure: number;
  /** Phase 5 feature `MonthlyCharges`. */
  monthlyCharges: number;
  /** Phase 5 feature `TotalCharges`. */
  totalCharges: number;
  /** Phase 5 feature `service_count`. */
  serviceCount: number;
  /** Phase 5 feature `contract_risk` (0 = lowest risk contract, 1 = highest). */
  contractRisk: number;
  contractType: ContractType;
  internetService: InternetService;
  techSupport: boolean;
  paymentMethod: PaymentMethod;
}

export interface PredictionResult {
  customerId: string;
  churnProbability: number;
  predictedLabel: ChurnLabel;
  riskBand: RiskBand;
  modelVersion: string;
  /** ISO date (YYYY-MM-DD) the customer was last scored. */
  scoredAt: string;
}

export interface ShapContribution {
  feature: string;
  /** Human-readable feature value, e.g. "4 months". */
  featureValue: string;
  /** Signed contribution in log-odds. Positive pushes towards churn. */
  contribution: number;
}

export interface ExplanationResult {
  customerId: string;
  /** Expected value (base value) of the model output in log-odds. */
  baseValue: number;
  contributions: ShapContribution[];
}

export interface RetentionAction {
  id: string;
  name: string;
  description: string;
  cost: number;
  successRate: number;
}

export interface ActionEvaluation {
  action: RetentionAction;
  expectedNetBenefit: number;
}

export interface BusinessResult {
  customerId: string;
  currency: string;
  clv: number;
  valueAtRisk: number;
  /** ENB of the best evaluated action (may be negative when no action pays off). */
  expectedNetBenefit: number;
  decision: InterventionDecision;
  /** Null when the decision is "Do not intervene". */
  bestAction: RetentionAction | null;
  /** All evaluated actions, sorted by ENB (descending). */
  actionOptions: ActionEvaluation[];
}

export interface SegmentResult {
  customerId: string;
  segmentId: SegmentId;
  clusterId: number;
  label: string;
}

export interface IntelligenceResult {
  customer: Customer;
  prediction: PredictionResult;
  explanation: ExplanationResult;
  business: BusinessResult;
  segment: SegmentResult;
}

export interface SegmentProfile {
  segmentId: SegmentId;
  clusterId: number;
  label: string;
  description: string;
  customerCount: number;
  /** Share of all customers, 0–100. */
  percentage: number;
  avgChurnProbability: number;
  avgClv: number;
  totalVar: number;
  /** Mean of each customer's best-action ENB. */
  avgEnb: number;
  /** Fraction (0–1) of customers with decision "Intervene". */
  interventionRate: number;
  interventionCount: number;
  recommendedAction: string;
}

export interface SegmentOverview {
  currency: string | null;
  totalCustomers: number;
  segments: SegmentProfile[];
}

export interface ActionSummary {
  actionId: string;
  action: string;
  customers: number;
  averageCost: number;
  successRate: number;
  expectedBenefit: number;
}

export interface DashboardMetrics {
  totalCustomers: number;
  highRiskCustomers: number;
  averageChurnProbability: number;
  totalValueAtRisk: number;
  retentionOpportunities: number;
  expectedNetBenefit: number;
}

export interface RiskDistributionPoint {
  band: RiskBand;
  count: number;
  percentage: number;
}

export interface ExposurePoint {
  band: RiskBand;
  customers: number;
  totalClv: number;
  valueAtRisk: number;
}

export interface DashboardData {
  currency: string | null;
  metrics: DashboardMetrics;
  riskDistribution: RiskDistributionPoint[];
  segmentProfiles: SegmentProfile[];
  exposureByRiskBand: ExposurePoint[];
  actionSummary: ActionSummary[];
  recentHighRisk: IntelligenceResult[];
}

export interface RetentionInsights {
  currency: string | null;
  highestValueAtRisk: IntelligenceResult[];
  highestVar: IntelligenceResult[];
  highestEnb: IntelligenceResult[];
  actionSummary: ActionSummary[];
  interventionCount: number;
  totalExpectedBenefit: number;
}

export type CustomerSortKey =
  | 'customerId'
  | 'churnProbability'
  | 'riskBand'
  | 'segment'
  | 'clv'
  | 'valueAtRisk'
  | 'expectedNetBenefit';

export type SortDirection = 'asc' | 'desc';

export interface CustomerQuery {
  search?: string;
  risk?: RiskBand | 'all';
  segment?: SegmentId | 'all';
  /** Minimum churn probability (0–1), inclusive. */
  minProbability?: number;
  sortBy?: CustomerSortKey;
  sortDirection?: SortDirection;
  page?: number;
  pageSize?: number;
}

export interface Page<T> {
  items: T[];
  total: number;
  page: number;
  pageSize: number;
  pageCount: number;
}

export interface WhatIfInput {
  customerId: string;
  actionId: string;
  actionCost: number;
  /** 0–1 */
  successRate: number;
  /** Scenario churn probability, 0–1 */
  churnProbability: number;
  /** Scenario CLV. */
  clv: number;
}

export interface WhatIfState {
  churnProbability: number;
  clv: number;
  valueAtRisk: number;
  actionId: string;
  actionName: string;
  actionCost: number;
  successRate: number;
  expectedNetBenefit: number;
  decision: InterventionDecision;
}

export interface WhatIfResult {
  customerId: string;
  label: 'Scenario / What-if analysis';
  current: WhatIfState;
  scenario: WhatIfState;
  deltaEnb: number;
}

export interface ChurnModelMetrics {
  rocAuc: number;
  prAuc: number;
  brierScore: number;
  logLoss: number;
  accuracy: number;
  precision: number;
  recall: number;
  f1: number;
}

export interface ChurnModelInfo {
  version: string;
  artifact: string;
  metrics: ChurnModelMetrics;
}

export interface SegmentationModelInfo {
  version: string;
  artifact: string;
  k: number;
  seed: number;
  features: string[];
}

export interface ModelInfo {
  churn: ChurnModelInfo;
  segmentation: SegmentationModelInfo;
  dataMode: DataMode;
}

export interface HealthStatus {
  status: 'ok' | 'degraded' | 'down';
  mode: DataMode;
  message: string;
}
