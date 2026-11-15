import { DEMO_ACTIONS } from '../../data/actions';
import { decisionFor, round, valueAtRisk, expectedNetBenefit } from '../../data/businessMath';
import { MOCK_INTELLIGENCE } from '../../data/mockDataset';
import { LOCKED_CHURN_MODEL, LOCKED_SEGMENTATION_MODEL } from '../../data/modelInfo';
import type {
  CustomerQuery,
  DashboardData,
  HealthStatus,
  IntelligenceResult,
  ModelInfo,
  Page,
  RetentionAction,
  RetentionInsights,
  SegmentOverview,
  WhatIfInput,
  WhatIfResult,
  WhatIfState,
} from '../../types';
import { ApiError, NotFoundError } from '../api/errors';
import type { DataProvider } from '../api/DataProvider';
import {
  buildDashboard,
  buildInsights,
  buildSegmentOverview,
  queryCustomers,
} from '../aggregations';

export interface MockProviderOptions {
  /** Artificial latency per call in ms (0 disables). */
  latencyMs?: number;
  /** "always" makes every call fail, to exercise error/retry UI. */
  failureMode?: 'none' | 'always';
  dataset?: readonly IntelligenceResult[];
}

const delay = (ms: number) => new Promise<void>((resolve) => setTimeout(resolve, ms));

/**
 * Development provider. Serves a fixed, deterministic DEMO dataset.
 * Never contacts a network. Not live or production data.
 */
export class MockDataProvider implements DataProvider {
  readonly name = 'MockDataProvider';
  readonly mode = 'mock' as const;

  private readonly latencyMs: number;
  private readonly data: readonly IntelligenceResult[];
  private failing: boolean;

  constructor(options: MockProviderOptions = {}) {
    this.latencyMs = options.latencyMs ?? 0;
    this.failing = options.failureMode === 'always';
    this.data = options.dataset ?? MOCK_INTELLIGENCE;
  }

  simulateFailure(enabled: boolean): void {
    this.failing = enabled;
  }

  isSimulatingFailure(): boolean {
    return this.failing;
  }

  private async respond<T>(compute: () => T): Promise<T> {
    if (this.latencyMs > 0) await delay(this.latencyMs);
    if (this.failing) {
      throw new ApiError('Simulated API failure (mock mode). Turn it off in Settings to recover.', 503);
    }
    return compute();
  }

  private find(customerId: string): IntelligenceResult {
    const key = customerId.trim().toUpperCase();
    const hit = this.data.find((r) => r.customer.customerId.toUpperCase() === key);
    if (!hit) throw new NotFoundError(`Customer "${customerId}" was not found.`);
    return hit;
  }

  getHealth(): Promise<HealthStatus> {
    return this.respond(() => ({
      status: 'ok' as const,
      mode: 'mock' as const,
      message: 'Mock data provider active — no API connected.',
    }));
  }

  getDashboard(): Promise<DashboardData> {
    return this.respond(() => buildDashboard(this.data, DEMO_ACTIONS));
  }

  listCustomers(query: CustomerQuery): Promise<Page<IntelligenceResult>> {
    return this.respond(() => queryCustomers(this.data, query));
  }

  getCustomer(customerId: string): Promise<IntelligenceResult> {
    return this.respond(() => this.find(customerId));
  }

  getSegments(): Promise<SegmentOverview> {
    return this.respond(() => buildSegmentOverview(this.data));
  }

  getInsights(): Promise<RetentionInsights> {
    return this.respond(() => buildInsights(this.data, DEMO_ACTIONS));
  }

  getActions(): Promise<RetentionAction[]> {
    return this.respond(() => [...DEMO_ACTIONS]);
  }

  runWhatIf(input: WhatIfInput): Promise<WhatIfResult> {
    return this.respond(() => {
      const base = this.find(input.customerId);
      const action = DEMO_ACTIONS.find((a) => a.id === input.actionId);
      if (!action) throw new ApiError(`Unknown action "${input.actionId}".`, 422);
      const invalid =
        !Number.isFinite(input.churnProbability) ||
        input.churnProbability < 0 ||
        input.churnProbability > 1 ||
        !Number.isFinite(input.successRate) ||
        input.successRate < 0 ||
        input.successRate > 1 ||
        !Number.isFinite(input.clv) ||
        input.clv < 0 ||
        !Number.isFinite(input.actionCost) ||
        input.actionCost < 0;
      if (invalid) throw new ApiError('Scenario inputs are out of range.', 422);

      const top = base.business.actionOptions[0];
      const current: WhatIfState = {
        churnProbability: base.prediction.churnProbability,
        clv: base.business.clv,
        valueAtRisk: base.business.valueAtRisk,
        actionId: top.action.id,
        actionName: top.action.name,
        actionCost: top.action.cost,
        successRate: top.action.successRate,
        expectedNetBenefit: top.expectedNetBenefit,
        decision: base.business.decision,
      };
      const enb = expectedNetBenefit(input.churnProbability, input.clv, input.successRate, input.actionCost);
      const scenario: WhatIfState = {
        churnProbability: input.churnProbability,
        clv: input.clv,
        valueAtRisk: valueAtRisk(input.churnProbability, input.clv),
        actionId: action.id,
        actionName: action.name,
        actionCost: input.actionCost,
        successRate: input.successRate,
        expectedNetBenefit: enb,
        decision: decisionFor(enb),
      };
      return {
        customerId: base.customer.customerId,
        label: 'Scenario / What-if analysis' as const,
        current,
        scenario,
        deltaEnb: round(scenario.expectedNetBenefit - current.expectedNetBenefit),
      };
    });
  }

  getModelInfo(): Promise<ModelInfo> {
    return this.respond(() => ({
      churn: LOCKED_CHURN_MODEL,
      segmentation: LOCKED_SEGMENTATION_MODEL,
      dataMode: 'mock' as const,
    }));
  }
}
