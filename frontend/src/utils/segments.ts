import type { SegmentId } from '../types';

/**
 * The three locked Phase 5 segment concepts (K = 3). This is a static
 * taxonomy used for labels and ordering only — the UI never re-derives
 * segment membership.
 */
export const SEGMENT_ORDER: readonly SegmentId[] = [
  'low-value-high-risk',
  'high-value-stable',
  'low-value-stable',
];

export const SEGMENT_META: Record<SegmentId, { clusterId: number; label: string; description: string }> = {
  'low-value-high-risk': {
    clusterId: 0,
    label: 'Low Value / High Risk',
    description: 'Short-tenure, flexible-contract customers with lower spend and elevated churn risk.',
  },
  'high-value-stable': {
    clusterId: 2,
    label: 'High Value / Stable',
    description: 'Long-tenure, higher-spend customers with a stable relationship.',
  },
  'low-value-stable': {
    clusterId: 1,
    label: 'Low Value / Stable',
    description: 'Lower-spend customers on longer commitments with stable behaviour.',
  },
};

export function isSegmentId(value: string | null | undefined): value is SegmentId {
  return value !== null && value !== undefined && (SEGMENT_ORDER as readonly string[]).includes(value);
}
