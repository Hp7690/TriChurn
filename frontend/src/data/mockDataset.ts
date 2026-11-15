import type {
  ChurnLabel,
  ContractType,
  Customer,
  ExplanationResult,
  InternetService,
  IntelligenceResult,
  PaymentMethod,
  SegmentId,
  ShapContribution,
} from '../types';
import { SEGMENT_META } from '../utils/segments';
import { DEMO_ACTIONS } from './actions';
import { buildBusinessResult, riskBandFor, round } from './businessMath';

/**
 * Deterministic DEMO dataset.
 *
 * Generated from a fixed seed with a pure PRNG, so every page load, test run
 * and machine produces exactly the same 80 customers. Nothing here is live or
 * production data.
 */

export const MOCK_CUSTOMER_COUNT = 80;
const SEED = 20250630;
const MODEL_VERSION = 'v2.0.0';
const BASE_PROBABILITY = 0.2;

function mulberry32(seed: number): () => number {
  let a = seed >>> 0;
  return () => {
    a = (a + 0x6d2b79f5) | 0;
    let t = Math.imul(a ^ (a >>> 15), 1 | a);
    t = (t + Math.imul(t ^ (t >>> 7), 61 | t)) ^ t;
    return ((t ^ (t >>> 14)) >>> 0) / 4294967296;
  };
}

const logit = (p: number) => Math.log(p / (1 - p));
const sigmoid = (z: number) => 1 / (1 + Math.exp(-z));
const clamp = (v: number, lo: number, hi: number) => Math.min(hi, Math.max(lo, v));

function pick<T>(rand: () => number, items: readonly T[], weights: readonly number[]): T {
  const r = rand();
  let acc = 0;
  for (let i = 0; i < items.length; i += 1) {
    acc += weights[i];
    if (r < acc) return items[i];
  }
  return items[items.length - 1];
}

function buildCustomer(index: number, rand: () => number): Customer {
  const contractType: ContractType = pick(
    rand,
    ['Month-to-month', 'One year', 'Two year'] as const,
    [0.52, 0.24, 0.24],
  );
  const contractRisk = contractType === 'Month-to-month' ? 1 : contractType === 'One year' ? 0.5 : 0;
  const internetService: InternetService = pick(
    rand,
    ['DSL', 'Fiber optic', 'None'] as const,
    [0.34, 0.46, 0.2],
  );
  const paymentMethod: PaymentMethod = pick(
    rand,
    ['Electronic check', 'Mailed check', 'Bank transfer', 'Credit card'] as const,
    [0.34, 0.2, 0.23, 0.23],
  );
  const tenureBias = contractType === 'Month-to-month' ? 1.6 : contractType === 'One year' ? 1 : 0.6;
  const tenure = 1 + Math.floor(Math.pow(rand(), tenureBias) * 71);
  const serviceCount =
    internetService === 'None' ? Math.floor(rand() * 3) : 1 + Math.floor(rand() * 8);
  const techSupport = internetService !== 'None' && rand() < 0.35;
  const base = internetService === 'Fiber optic' ? 70 : internetService === 'DSL' ? 45 : 22;
  const monthlyCharges = round(base + serviceCount * 4.5 + (rand() - 0.5) * 10, 2);
  const totalCharges = round(monthlyCharges * tenure * (0.94 + rand() * 0.1), 2);

  return {
    customerId: `TC-${String(1001 + index)}`,
    tenure,
    monthlyCharges,
    totalCharges,
    serviceCount,
    contractRisk,
    contractType,
    internetService,
    techSupport,
    paymentMethod,
  };
}

function explain(customer: Customer): ExplanationResult {
  const raw: ShapContribution[] = [
    {
      feature: 'tenure',
      featureValue: `${customer.tenure} months`,
      contribution: clamp(-0.03 * (customer.tenure - 32), -1.1, 1.0),
    },
    {
      feature: 'MonthlyCharges',
      featureValue: `$${customer.monthlyCharges.toFixed(2)}`,
      contribution: clamp(0.012 * (customer.monthlyCharges - 65), -0.6, 0.6),
    },
    {
      feature: 'TotalCharges',
      featureValue: `$${customer.totalCharges.toFixed(0)}`,
      contribution: clamp(-0.00015 * (customer.totalCharges - 2200), -0.8, 0.5),
    },
    {
      feature: 'service_count',
      featureValue: String(customer.serviceCount),
      contribution: clamp(-0.08 * (customer.serviceCount - 3.5), -0.5, 0.5),
    },
    {
      feature: 'contract_risk',
      featureValue: `${customer.contractType} (${customer.contractRisk})`,
      contribution: (customer.contractRisk - 0.5) * 1.6,
    },
    {
      feature: 'InternetService',
      featureValue: customer.internetService,
      contribution:
        customer.internetService === 'Fiber optic' ? 0.45 : customer.internetService === 'DSL' ? -0.05 : -0.5,
    },
    {
      feature: 'TechSupport',
      featureValue: customer.techSupport ? 'Yes' : customer.internetService === 'None' ? 'No internet' : 'No',
      contribution: customer.techSupport ? -0.3 : customer.internetService === 'None' ? 0 : 0.15,
    },
    {
      feature: 'PaymentMethod',
      featureValue: customer.paymentMethod,
      contribution: customer.paymentMethod === 'Electronic check' ? 0.35 : -0.1,
    },
  ];
  const contributions = raw
    .map((c) => ({ ...c, contribution: round(c.contribution, 3) }))
    .sort((a, b) => Math.abs(b.contribution) - Math.abs(a.contribution) || a.feature.localeCompare(b.feature));
  return {
    customerId: customer.customerId,
    baseValue: round(logit(BASE_PROBABILITY), 3),
    contributions,
  };
}

function segmentFor(customer: Customer): SegmentId {
  if (customer.tenure >= 36 && customer.monthlyCharges >= 70) return 'high-value-stable';
  if (customer.contractRisk === 1 && customer.tenure < 24) return 'low-value-high-risk';
  return 'low-value-stable';
}

function deepFreeze<T>(value: T): T {
  if (value !== null && typeof value === 'object' && !Object.isFrozen(value)) {
    Object.freeze(value);
    Object.values(value as Record<string, unknown>).forEach((v) => deepFreeze(v));
  }
  return value;
}

export function buildMockIntelligence(count: number = MOCK_CUSTOMER_COUNT): IntelligenceResult[] {
  const rand = mulberry32(SEED);
  const results: IntelligenceResult[] = [];

  for (let index = 0; index < count; index += 1) {
    const customer = buildCustomer(index, rand);
    const explanation = explain(customer);
    const logOdds = explanation.baseValue + explanation.contributions.reduce((s, c) => s + c.contribution, 0);
    const churnProbability = round(sigmoid(logOdds), 4);
    const clv = Math.round(
      customer.monthlyCharges *
        (10 + customer.tenure * 0.5 + (customer.contractRisk === 0 ? 12 : customer.contractRisk === 0.5 ? 6 : 0)),
    );
    const segmentId = segmentFor(customer);
    const predictedLabel: ChurnLabel = churnProbability >= 0.5 ? 'Churn' : 'No Churn';
    const scoredAt = new Date(Date.UTC(2025, 5, 30 - ((index * 11) % 28))).toISOString().slice(0, 10);

    results.push({
      customer,
      prediction: {
        customerId: customer.customerId,
        churnProbability,
        predictedLabel,
        riskBand: riskBandFor(churnProbability),
        modelVersion: MODEL_VERSION,
        scoredAt,
      },
      explanation,
      business: buildBusinessResult(customer.customerId, churnProbability, clv, DEMO_ACTIONS),
      segment: {
        customerId: customer.customerId,
        segmentId,
        clusterId: SEGMENT_META[segmentId].clusterId,
        label: SEGMENT_META[segmentId].label,
      },
    });
  }
  return results;
}

export const MOCK_INTELLIGENCE: readonly IntelligenceResult[] = deepFreeze(buildMockIntelligence());
