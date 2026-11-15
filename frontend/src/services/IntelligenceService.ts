import type {
  CustomerQuery,
  DashboardData,
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
} from '../types';
import type { DataProvider } from './api/DataProvider';
import { NotFoundError } from './api/errors';

/**
 * The only object UI code talks to. It delegates to whichever `DataProvider`
 * it was constructed with, and normalises inputs (e.g. URL-encoded ids).
 */
export class IntelligenceService {
  constructor(private readonly provider: DataProvider) {}

  get providerName(): string {
    return this.provider.name;
  }

  get mode(): DataMode {
    return this.provider.mode;
  }

  get canSimulateFailure(): boolean {
    return typeof this.provider.simulateFailure === 'function';
  }

  setSimulatedFailure(enabled: boolean): void {
    this.provider.simulateFailure?.(enabled);
  }

  get isSimulatingFailure(): boolean {
    return this.provider.isSimulatingFailure?.() ?? false;
  }

  getHealth(): Promise<HealthStatus> {
    return this.provider.getHealth();
  }
  getDashboard(): Promise<DashboardData> {
    return this.provider.getDashboard();
  }
  listCustomers(query: CustomerQuery): Promise<Page<IntelligenceResult>> {
    return this.provider.listCustomers(query);
  }
  getCustomer(rawId: string): Promise<IntelligenceResult> {
    const id = rawId.trim();
    if (id === '') return Promise.reject(new NotFoundError('No customer ID was provided.'));
    return this.provider.getCustomer(id);
  }
  getSegments(): Promise<SegmentOverview> {
    return this.provider.getSegments();
  }
  getInsights(): Promise<RetentionInsights> {
    return this.provider.getInsights();
  }
  getActions(): Promise<RetentionAction[]> {
    return this.provider.getActions();
  }
  runWhatIf(input: WhatIfInput): Promise<WhatIfResult> {
    return this.provider.runWhatIf(input);
  }
  getModelInfo(): Promise<ModelInfo> {
    return this.provider.getModelInfo();
  }
}
