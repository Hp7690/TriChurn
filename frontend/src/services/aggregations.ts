import type {
  ActionSummary,
  CustomerQuery,
  CustomerSortKey,
  DashboardData,
  ExposurePoint,
  IntelligenceResult,
  Page,
  RetentionAction,
  RetentionInsights,
  RiskBand,
  SegmentOverview,
  SegmentProfile,
} from '../types';
import { round } from '../data/businessMath';
import { RISK_BANDS } from '../utils/theme';
import { SEGMENT_META, SEGMENT_ORDER } from '../utils/segments';

/**
 * Pure, provider-agnostic roll-ups over per-customer intelligence results.
 * They only AGGREGATE values already present on each result (no new business
 * or ML logic), so a future FastAPI provider can reuse them as well.
 */

export const DEFAULT_PAGE_SIZE = 10;
const RISK_RANK: Record<RiskBand, number> = { Low: 0, Medium: 1, High: 2 };

const isIntervene = (r: IntelligenceResult) => r.business.decision === 'Intervene';
const sum = (values: number[]) => values.reduce((acc, v) => acc + v, 0);
const mean = (values: number[]) => (values.length === 0 ? 0 : sum(values) / values.length);

/** Aggregated monetary values require one consistent currency. */
function getPortfolioCurrency(items: readonly IntelligenceResult[]): string | null {
  const currencies = new Set(
    items.map((item) => (item.business.currency || 'USD').toUpperCase()),
  );
  if (currencies.size > 1) {
    throw new Error(
      `Cannot aggregate mixed currencies: ${[...currencies].sort().join(', ')}. Convert currencies before aggregation.`,
    );
  }
  return [...currencies][0] ?? null;
}


export function buildActionSummary(
  items: readonly IntelligenceResult[],
  actions: readonly RetentionAction[],
): ActionSummary[] {
  return actions
    .map((action) => {
      const group = items.filter((r) => isIntervene(r) && r.business.bestAction?.id === action.id);
      return {
        actionId: action.id,
        action: action.name,
        customers: group.length,
        averageCost: action.cost,
        successRate: action.successRate,
        expectedBenefit: round(sum(group.map((r) => r.business.expectedNetBenefit))),
      };
    })
    .sort((a, b) => b.expectedBenefit - a.expectedBenefit || a.actionId.localeCompare(b.actionId));
}

export function buildSegmentProfiles(items: readonly IntelligenceResult[]): SegmentProfile[] {
  return SEGMENT_ORDER.map((segmentId) => {
    const group = items.filter((r) => r.segment.segmentId === segmentId);
    const intervene = group.filter(isIntervene);
    const counts = new Map<string, number>();
    intervene.forEach((r) => {
      const name = r.business.bestAction?.name;
      if (name) counts.set(name, (counts.get(name) ?? 0) + 1);
    });
    const top = [...counts.entries()].sort((a, b) => b[1] - a[1] || a[0].localeCompare(b[0]))[0];
    const meta = SEGMENT_META[segmentId];
    return {
      segmentId,
      clusterId: meta.clusterId,
      label: meta.label,
      description: meta.description,
      customerCount: group.length,
      percentage: items.length === 0 ? 0 : round((group.length / items.length) * 100, 1),
      avgChurnProbability: round(mean(group.map((r) => r.prediction.churnProbability)), 4),
      avgClv: round(mean(group.map((r) => r.business.clv))),
      totalVar: round(sum(group.map((r) => r.business.valueAtRisk))),
      avgEnb: round(mean(group.map((r) => r.business.expectedNetBenefit))),
      interventionRate: group.length === 0 ? 0 : round(intervene.length / group.length, 4),
      interventionCount: intervene.length,
      recommendedAction: top ? top[0] : 'Monitor — no action recommended',
    };
  });
}

export function buildSegmentOverview(items: readonly IntelligenceResult[]): SegmentOverview {
  return {
    currency: getPortfolioCurrency(items),
    totalCustomers: items.length,
    segments: buildSegmentProfiles(items),
  };
}

export function buildDashboard(
  items: readonly IntelligenceResult[],
  actions: readonly RetentionAction[],
): DashboardData {
  const total = items.length;
  const intervene = items.filter(isIntervene);
  const high = items.filter((r) => r.prediction.riskBand === 'High');
  const actionSummary = buildActionSummary(items, actions);

  const exposureByRiskBand: ExposurePoint[] = RISK_BANDS.map((band) => {
    const group = items.filter((r) => r.prediction.riskBand === band);
    return {
      band,
      customers: group.length,
      totalClv: round(sum(group.map((r) => r.business.clv))),
      valueAtRisk: round(sum(group.map((r) => r.business.valueAtRisk))),
    };
  });

  const recentHighRisk = [...high]
    .sort(
      (a, b) =>
        b.prediction.scoredAt.localeCompare(a.prediction.scoredAt) ||
        b.prediction.churnProbability - a.prediction.churnProbability ||
        a.prediction.customerId.localeCompare(b.prediction.customerId),
    )
    .slice(0, 6);

  return {
    currency: getPortfolioCurrency(items),
    metrics: {
      totalCustomers: total,
      highRiskCustomers: high.length,
      averageChurnProbability: round(mean(items.map((r) => r.prediction.churnProbability)), 4),
      totalValueAtRisk: round(sum(items.map((r) => r.business.valueAtRisk))),
      retentionOpportunities: intervene.length,
      expectedNetBenefit: round(sum(intervene.map((r) => r.business.expectedNetBenefit))),
    },
    riskDistribution: RISK_BANDS.map((band) => {
      const count = items.filter((r) => r.prediction.riskBand === band).length;
      return { band, count, percentage: total === 0 ? 0 : round((count / total) * 100, 1) };
    }),
    segmentProfiles: buildSegmentProfiles(items),
    exposureByRiskBand,
    actionSummary,
    recentHighRisk,
  };
}

export function buildInsights(
  items: readonly IntelligenceResult[],
  actions: readonly RetentionAction[],
  topN = 5,
): RetentionInsights {
  const byDesc = (select: (r: IntelligenceResult) => number) => (a: IntelligenceResult, b: IntelligenceResult) =>
    select(b) - select(a) || a.prediction.customerId.localeCompare(b.prediction.customerId);
  const intervene = items.filter(isIntervene);
  const actionSummary = buildActionSummary(items, actions);
  return {
    currency: getPortfolioCurrency(items),
    highestValueAtRisk: items
      .filter((r) => r.prediction.riskBand !== 'Low')
      .sort(byDesc((r) => r.business.clv))
      .slice(0, topN),
    highestVar: [...items].sort(byDesc((r) => r.business.valueAtRisk)).slice(0, topN),
    highestEnb: [...intervene].sort(byDesc((r) => r.business.expectedNetBenefit)).slice(0, topN),
    actionSummary,
    interventionCount: intervene.length,
    totalExpectedBenefit: round(sum(actionSummary.map((action) => action.expectedBenefit))),
  };
}

function sortValue(item: IntelligenceResult, key: CustomerSortKey): number | string {
  switch (key) {
    case 'customerId':
      return item.prediction.customerId;
    case 'churnProbability':
      return item.prediction.churnProbability;
    case 'riskBand':
      return RISK_RANK[item.prediction.riskBand];
    case 'segment':
      return item.segment.label;
    case 'clv':
      return item.business.clv;
    case 'valueAtRisk':
      return item.business.valueAtRisk;
    case 'expectedNetBenefit':
      return item.business.expectedNetBenefit;
  }
}

export function queryCustomers(items: readonly IntelligenceResult[], query: CustomerQuery): Page<IntelligenceResult> {
  const search = (query.search ?? '').trim().toLowerCase();
  const risk = query.risk ?? 'all';
  const segment = query.segment ?? 'all';
  const minProbability = query.minProbability ?? 0;
  const sortBy = query.sortBy ?? 'churnProbability';
  const direction = query.sortDirection ?? 'desc';
  const pageSize = Math.min(500, Math.max(1, Math.floor(query.pageSize ?? DEFAULT_PAGE_SIZE)));

  const filtered = items.filter(
    (r) =>
      (search === '' || r.prediction.customerId.toLowerCase().includes(search)) &&
      (risk === 'all' || r.prediction.riskBand === risk) &&
      (segment === 'all' || r.segment.segmentId === segment) &&
      r.prediction.churnProbability >= minProbability,
  );

  const sign = direction === 'asc' ? 1 : -1;
  const sorted = [...filtered].sort((a, b) => {
    const av = sortValue(a, sortBy);
    const bv = sortValue(b, sortBy);
    if (av < bv) return -1 * sign;
    if (av > bv) return 1 * sign;
    return a.prediction.customerId.localeCompare(b.prediction.customerId);
  });

  const pageCount = Math.max(1, Math.ceil(sorted.length / pageSize));
  const page = Math.min(pageCount, Math.max(1, Math.floor(query.page ?? 1)));
  return {
    items: sorted.slice((page - 1) * pageSize, page * pageSize),
    total: sorted.length,
    page,
    pageSize,
    pageCount,
  };
}
