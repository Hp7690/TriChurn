import type {
  ActionEvaluation,
  BusinessResult,
  InterventionDecision,
  RetentionAction,
  RiskBand,
} from '../types';

/**
 * Mock-provider business helpers.
 *
 * IMPORTANT: these exist so the demo dataset is internally consistent. They
 * are a conventional expected-value shape (VaR = p × CLV,
 * ENB = p × success × CLV − cost), used ONLY inside the mock adapter. The real
 * numbers come from the locked Phase 4 engine via Phase 6. UI components never
 * call these functions.
 */

export const RISK_THRESHOLDS = { medium: 0.3, high: 0.6 } as const;

export function round(value: number, digits = 2): number {
  const factor = 10 ** digits;
  return Math.round(value * factor) / factor;
}

export function riskBandFor(probability: number): RiskBand {
  if (probability >= RISK_THRESHOLDS.high) return 'High';
  if (probability >= RISK_THRESHOLDS.medium) return 'Medium';
  return 'Low';
}

export function valueAtRisk(probability: number, clv: number): number {
  return round(probability * clv);
}

export function expectedNetBenefit(
  probability: number,
  clv: number,
  successRate: number,
  cost: number,
): number {
  return round(probability * successRate * clv - cost);
}

export function decisionFor(enb: number): InterventionDecision {
  return enb > 0 ? 'Intervene' : 'Do not intervene';
}

export function evaluateActions(
  probability: number,
  clv: number,
  actions: readonly RetentionAction[],
): ActionEvaluation[] {
  return actions
    .map((action) => ({
      action,
      expectedNetBenefit: expectedNetBenefit(probability, clv, action.successRate, action.cost),
    }))
    .sort((a, b) => b.expectedNetBenefit - a.expectedNetBenefit || a.action.id.localeCompare(b.action.id));
}

export function buildBusinessResult(
  customerId: string,
  probability: number,
  clv: number,
  actions: readonly RetentionAction[],
): BusinessResult {
  const options = evaluateActions(probability, clv, actions);
  const top = options[0];
  const decision = decisionFor(top.expectedNetBenefit);
  return {
    customerId,
    currency: 'USD',
    clv,
    valueAtRisk: valueAtRisk(probability, clv),
    expectedNetBenefit: top.expectedNetBenefit,
    decision,
    bestAction: decision === 'Intervene' ? top.action : null,
    actionOptions: options,
  };
}
