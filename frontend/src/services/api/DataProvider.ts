import type {
  DashboardData,
  CustomerQuery,
  DataMode,
  HealthStatus,
  IntelligenceResult,
  ModelInfo,
  Page,
  RetentionAction,
  RetentionInsights,
  SegmentOverview,
  WhatIfInput,
  WhatIfResult,
} from '../../types';

/**
 * The single seam between the UI and any data source.
 *
 * Implementations:
 *  - `MockDataProvider`    (deterministic demo data, no backend)
 *  - `FastAPIDataProvider` (Phase 6 FastAPI integration)
 *
 * UI code must only depend on this interface (through `IntelligenceService`).
 */
export interface DataProvider {
  readonly name: string;
  readonly mode: DataMode;

  getHealth(): Promise<HealthStatus>;
  getDashboard(): Promise<DashboardData>;
  listCustomers(query: CustomerQuery): Promise<Page<IntelligenceResult>>;
  /** Rejects with `NotFoundError` for an unknown customer. */
  getCustomer(customerId: string): Promise<IntelligenceResult>;
  getSegments(): Promise<SegmentOverview>;
  getInsights(): Promise<RetentionInsights>;
  getActions(): Promise<RetentionAction[]>;
  runWhatIf(input: WhatIfInput): Promise<WhatIfResult>;
  getModelInfo(): Promise<ModelInfo>;

  /** Development-only hook (mock mode): force every call to fail to exercise error UI. */
  simulateFailure?(enabled: boolean): void;
  isSimulatingFailure?(): boolean;
}
