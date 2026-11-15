import axios from 'axios';
import { describe, expect, it, vi } from 'vitest';
import { riskBandFor, valueAtRisk } from '../data/businessMath';
import { MOCK_CUSTOMER_COUNT, MOCK_INTELLIGENCE, buildMockIntelligence } from '../data/mockDataset';
import { LOCKED_CHURN_MODEL, LOCKED_SEGMENTATION_MODEL } from '../data/modelInfo';
import { MockDataProvider } from '../services/adapters/MockDataProvider';
import { FastAPIDataProvider } from '../services/adapters/FastAPIDataProvider';
import { ApiError, NotFoundError } from '../services/api/errors';
import { IntelligenceService } from '../services/IntelligenceService';
import { SEGMENT_META, SEGMENT_ORDER } from '../utils/segments';

function assertNoUndefined(value: unknown, path = 'root'): void {
  // `bestAction` is legitimately null when the decision is "Do not intervene".
  if (value === null && path.endsWith('.bestAction')) return;
  if (value === undefined || value === null) throw new Error(`Missing value at ${path}`);
  if (typeof value === 'number' && !Number.isFinite(value)) throw new Error(`Non-finite number at ${path}`);
  if (Array.isArray(value)) value.forEach((v, i) => assertNoUndefined(v, `${path}[${i}]`));
  else if (typeof value === 'object') {
    Object.entries(value as Record<string, unknown>).forEach(([k, v]) => assertNoUndefined(v, `${path}.${k}`));
  }
}

describe('mock dataset', () => {
  it('has the expected number of unique customers', () => {
    expect(MOCK_INTELLIGENCE).toHaveLength(MOCK_CUSTOMER_COUNT);
    expect(new Set(MOCK_INTELLIGENCE.map((r) => r.customer.customerId)).size).toBe(MOCK_CUSTOMER_COUNT);
  });

  it('is deterministic across rebuilds', () => {
    expect(JSON.stringify(buildMockIntelligence())).toBe(JSON.stringify(buildMockIntelligence()));
    expect(JSON.stringify(buildMockIntelligence())).toBe(JSON.stringify(MOCK_INTELLIGENCE));
  });

  it('has every critical field defined and finite', () => {
    MOCK_INTELLIGENCE.forEach((r) => assertNoUndefined(r, r.customer.customerId));
  });

  it('keeps probability, band, VaR, decision, segment and SHAP values internally consistent', () => {
    MOCK_INTELLIGENCE.forEach((r) => {
      const p = r.prediction.churnProbability;
      expect(p).toBeGreaterThanOrEqual(0);
      expect(p).toBeLessThanOrEqual(1);
      expect(r.prediction.riskBand).toBe(riskBandFor(p));
      expect(r.business.valueAtRisk).toBe(valueAtRisk(p, r.business.clv));
      expect(r.business.decision === 'Intervene').toBe(r.business.expectedNetBenefit > 0);
      expect(r.business.bestAction === null).toBe(r.business.decision === 'Do not intervene');
      expect(SEGMENT_ORDER).toContain(r.segment.segmentId);
      expect(r.explanation.contributions.length).toBeGreaterThan(0);
      const logOdds = r.explanation.baseValue + r.explanation.contributions.reduce((s, c) => s + c.contribution, 0);
      expect(1 / (1 + Math.exp(-logOdds))).toBeCloseTo(p, 2);
    });
  });
});

describe('MockDataProvider', () => {
  it('returns identical results for the same customer across provider instances', async () => {
    const a = await new MockDataProvider().getCustomer('TC-1001');
    const b = await new MockDataProvider().getCustomer('TC-1001');
    expect(a).toEqual(b);
    expect(await new MockDataProvider().getDashboard()).toEqual(await new MockDataProvider().getDashboard());
  });

  it('finds customers case-insensitively and rejects unknown ids with NotFoundError', async () => {
    const provider = new MockDataProvider();
    expect((await provider.getCustomer(' tc-1001 ')).customer.customerId).toBe('TC-1001');
    await expect(provider.getCustomer('TC-9999')).rejects.toBeInstanceOf(NotFoundError);
  });

  it('filters, sorts and paginates customers', async () => {
    const provider = new MockDataProvider();
    const high = await provider.listCustomers({ risk: 'High', pageSize: 500 });
    expect(high.total).toBeGreaterThan(0);
    expect(high.items.every((r) => r.prediction.riskBand === 'High')).toBe(true);

    const seg = await provider.listCustomers({ segment: 'low-value-high-risk', pageSize: 500 });
    expect(seg.items.every((r) => r.segment.segmentId === 'low-value-high-risk')).toBe(true);

    const min = await provider.listCustomers({ minProbability: 0.5, pageSize: 500 });
    expect(min.items.every((r) => r.prediction.churnProbability >= 0.5)).toBe(true);

    const sorted = await provider.listCustomers({ sortBy: 'valueAtRisk', sortDirection: 'desc', pageSize: 500 });
    const vars = sorted.items.map((r) => r.business.valueAtRisk);
    expect(vars).toEqual([...vars].sort((x, y) => y - x));

    const search = await provider.listCustomers({ search: 'tc-1005' });
    expect(search.total).toBe(1);

    const first = await provider.listCustomers({ page: 1, pageSize: 10 });
    expect(first.items).toHaveLength(10);
    expect(first.total).toBe(MOCK_CUSTOMER_COUNT);
    expect(first.pageCount).toBe(8);
    const clamped = await provider.listCustomers({ page: 999, pageSize: 10 });
    expect(clamped.page).toBe(8);
  });

  it('builds segment profiles for the three locked segments that cover every customer', async () => {
    const overview = await new MockDataProvider().getSegments();
    expect(overview.segments.map((s) => s.segmentId)).toEqual([...SEGMENT_ORDER]);
    expect(overview.segments.map((s) => s.label)).toEqual([
      'Low Value / High Risk',
      'High Value / Stable',
      'Low Value / Stable',
    ]);
    expect(overview.segments.reduce((s, p) => s + p.customerCount, 0)).toBe(MOCK_CUSTOMER_COUNT);
    expect(SEGMENT_META['high-value-stable'].clusterId).toBe(2);
    expect(SEGMENT_META['low-value-stable'].clusterId).toBe(1);
  });

  it('builds dashboard metrics that match the underlying customers', async () => {
    const d = await new MockDataProvider().getDashboard();
    expect(d.metrics.totalCustomers).toBe(MOCK_CUSTOMER_COUNT);
    expect(d.metrics.highRiskCustomers).toBe(MOCK_INTELLIGENCE.filter((r) => r.prediction.riskBand === 'High').length);
    expect(d.metrics.retentionOpportunities).toBe(
      MOCK_INTELLIGENCE.filter((r) => r.business.decision === 'Intervene').length,
    );
    expect(d.riskDistribution.reduce((s, p) => s + p.count, 0)).toBe(MOCK_CUSTOMER_COUNT);
    expect(d.recentHighRisk.every((r) => r.prediction.riskBand === 'High')).toBe(true);
    assertNoUndefined(d);
  });

  it('keeps portfolio expected benefit equal to the sum of its action breakdown', async () => {
    const insights = await new MockDataProvider().getInsights();
    expect(insights.totalExpectedBenefit).toBeCloseTo(
      insights.actionSummary.reduce((total, action) => total + action.expectedBenefit, 0),
      2,
    );
  });

  it('runs a what-if scenario and reports no change when inputs equal the current state', async () => {
    const provider = new MockDataProvider();
    const base = await provider.getCustomer('TC-1002');
    const top = base.business.actionOptions[0].action;
    const result = await provider.runWhatIf({
      customerId: 'TC-1002',
      actionId: top.id,
      actionCost: top.cost,
      successRate: top.successRate,
      churnProbability: base.prediction.churnProbability,
      clv: base.business.clv,
    });
    expect(result.label).toBe('Scenario / What-if analysis');
    expect(result.deltaEnb).toBe(0);
    expect(result.scenario.decision).toBe(result.current.decision);
  });

  it('rejects invalid what-if input', async () => {
    const provider = new MockDataProvider();
    const input = { customerId: 'TC-1001', actionId: 'loyalty-discount', actionCost: 10, successRate: 0.2, churnProbability: 0.5, clv: 1000 };
    await expect(provider.runWhatIf({ ...input, churnProbability: 1.5 })).rejects.toBeInstanceOf(ApiError);
    await expect(provider.runWhatIf({ ...input, actionId: 'nope' })).rejects.toBeInstanceOf(ApiError);
  });

  it('can simulate failure and recover', async () => {
    const provider = new MockDataProvider();
    provider.simulateFailure(true);
    await expect(provider.getDashboard()).rejects.toBeInstanceOf(ApiError);
    provider.simulateFailure(false);
    expect((await provider.getDashboard()).metrics.totalCustomers).toBe(MOCK_CUSTOMER_COUNT);
  });

  it('serves the locked Phase 2 and Phase 5 model information unchanged', async () => {
    const info = await new MockDataProvider().getModelInfo();
    expect(info.churn.metrics).toEqual({
      rocAuc: 0.8492,
      prAuc: 0.6412,
      brierScore: 0.1355,
      logLoss: 0.4107,
      accuracy: 0.7711,
      precision: 0.5503,
      recall: 0.7429,
      f1: 0.6322,
    });
    expect(info.churn).toEqual(LOCKED_CHURN_MODEL);
    expect(info.segmentation).toEqual(LOCKED_SEGMENTATION_MODEL);
    expect(info.segmentation.k).toBe(3);
    expect(info.segmentation.seed).toBe(42);
    expect(info.segmentation.features).toEqual(['tenure', 'MonthlyCharges', 'TotalCharges', 'service_count', 'contract_risk']);
  });
});

describe('IntelligenceService and FastAPI skeleton', () => {
  it('rejects an empty customer id before reaching the provider', async () => {
    const service = new IntelligenceService(new MockDataProvider());
    await expect(service.getCustomer('   ')).rejects.toBeInstanceOf(NotFoundError);
  });

  it('exposes provider metadata', () => {
    const service = new IntelligenceService(new MockDataProvider());
    expect(service.mode).toBe('mock');
    expect(service.providerName).toBe('MockDataProvider');
  });

  it('loads all live customers before calculating dashboard metrics', async () => {
    const csv = [
      'customerID,gender,SeniorCitizen,Partner,Dependents,tenure,PhoneService,MultipleLines,InternetService,OnlineSecurity,OnlineBackup,DeviceProtection,TechSupport,StreamingTV,StreamingMovies,Contract,PaperlessBilling,PaymentMethod,MonthlyCharges,TotalCharges',
      'C-1,Female,0,Yes,No,12,Yes,No,DSL,Yes,No,No,Yes,No,No,One year,Yes,Electronic check,55,660',
      'C-2,Male,0,No,No,24,Yes,No,Fiber optic,No,Yes,No,No,Yes,Yes,Two year,No,Mailed check,70,1680',
      'C-3,Female,0,Yes,Yes,36,Yes,Yes,DSL,Yes,Yes,Yes,Yes,Yes,Yes,Two year,No,Credit card (automatic),80,2880',
    ].join('\n');
    const fetchMock = vi.fn().mockResolvedValue({
      ok: true,
      text: async () => csv,
    });
    vi.stubGlobal('fetch', fetchMock);

    const post = vi.fn(async (_url: string, request: {
      customer_id: string;
      features: Record<string, unknown>;
    }) => {
      const highRisk = request.customer_id === 'C-1';
      const clusterId = request.customer_id === 'C-1' ? 0 : request.customer_id === 'C-2' ? 1 : 2;
      const segmentName = ['Low Value / High Risk', 'Low Value / Stable', 'High Value / Stable'][clusterId];
      return {
        data: {
          customer_id: request.customer_id,
          prediction: {
            customer_id: request.customer_id,
            churn_probability: highRisk ? 0.8 : 0.2,
            predicted_churn: highRisk,
            risk_band: highRisk ? 'CRITICAL' : 'LOW',
            model_version: '2.0.0',
          },
          explanation: { base_value: 0, features: [] },
          business: {
            currency: 'USD',
            clv: 100,
            value_at_risk: highRisk ? 80 : 20,
            expected_net_benefit: highRisk ? 12 : 0,
            intervention_decision: highRisk ? 'INTERVENE' : 'DO_NOT_INTERVENE',
            recommended_action_id: highRisk ? 'retention-offer' : 'no_action',
            action_evaluations: [{
              action_id: 'retention-offer',
              name: 'Retention offer',
              description: 'A test action',
              cost: 10,
              success_rate: 0.5,
              expected_net_benefit: 12,
            }],
          },
          segment: { segment_id: clusterId, segment_name: segmentName },
        },
      };
    });
    const createSpy = vi.spyOn(axios, 'create').mockReturnValue(
      { post } as unknown as ReturnType<typeof axios.create>,
    );

    try {
      const provider = new FastAPIDataProvider({ baseUrl: 'http://localhost:8000' });
      const dashboards = await Promise.all([provider.getDashboard(), provider.getDashboard()]);

      expect(fetchMock).toHaveBeenCalledOnce();
      expect(post).toHaveBeenCalledTimes(3);
      expect(Object.keys(post.mock.calls[0][1].features).sort()).toEqual([
        'Contract',
        'Dependents',
        'DeviceProtection',
        'InternetService',
        'MonthlyCharges',
        'MultipleLines',
        'OnlineBackup',
        'OnlineSecurity',
        'PaperlessBilling',
        'Partner',
        'PaymentMethod',
        'PhoneService',
        'SeniorCitizen',
        'StreamingMovies',
        'StreamingTV',
        'TechSupport',
        'TotalCharges',
        'gender',
        'tenure',
      ]);
      dashboards.forEach((dashboard) => {
        expect(dashboard.metrics.totalCustomers).toBe(3);
        expect(dashboard.metrics.highRiskCustomers).toBe(1);
      });
      const lowRisk = await provider.listCustomers({ risk: 'Low', pageSize: 500 });
      const highRisk = await provider.listCustomers({ risk: 'High', pageSize: 500 });
      expect(lowRisk.total).toBe(2);
      expect(lowRisk.items.every((item) => item.prediction.riskBand === 'Low')).toBe(true);
      expect(highRisk.total).toBe(1);
      expect(highRisk.items.every((item) => item.prediction.riskBand === 'High')).toBe(true);

      const lowValueStable = await provider.listCustomers({ segment: 'low-value-stable', pageSize: 500 });
      const highValueStable = await provider.listCustomers({ segment: 'high-value-stable', pageSize: 500 });
      expect(lowValueStable.items.map((item) => item.prediction.customerId)).toEqual(['C-2']);
      expect(highValueStable.items.map((item) => item.prediction.customerId)).toEqual(['C-3']);
    } finally {
      createSpy.mockRestore();
      vi.unstubAllGlobals();
    }
  });
});
