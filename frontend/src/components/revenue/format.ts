/** Formatting helpers. A null value NEVER becomes "0": it renders as an explicit unavailable marker. */
import type { EvidenceStatus, Metric } from '../../types/revenue';

export const UNAVAILABLE_TEXT = 'Unavailable';

export function formatNumber(v: number | null | undefined, digits = 0): string {
  if (v === null || v === undefined || Number.isNaN(v)) return UNAVAILABLE_TEXT;
  return v.toLocaleString('en-US', { minimumFractionDigits: digits, maximumFractionDigits: digits });
}
/** Currency units exactly as in the source data (the dataset declares no currency symbol). */
export function formatMoney(v: number | null | undefined): string {
  return formatNumber(v, 2);
}
export function formatPercent(v: number | null | undefined, digits = 1): string {
  if (v === null || v === undefined || Number.isNaN(v)) return UNAVAILABLE_TEXT;
  return `${(v * 100).toFixed(digits)}%`;
}
export function formatMetricValue(m: Metric): string {
  if (m.value === null || m.status === 'UNAVAILABLE' || m.status === 'BLOCKED_BY_MISSING_DATA') {
    return m.status === 'BLOCKED_BY_MISSING_DATA' ? 'Blocked' : UNAVAILABLE_TEXT;
  }
  if (typeof m.value === 'string') return m.value;
  if (m.unit === 'ratio') return formatPercent(m.value);
  if (m.unit === 'count') return formatNumber(m.value);
  if (m.unit === 'currency') return formatMoney(m.value);
  return formatNumber(m.value, 2);
}
export function isNullStatus(s: EvidenceStatus): boolean {
  return s === 'UNAVAILABLE' || s === 'BLOCKED_BY_MISSING_DATA';
}
export function titleCase(s: string): string {
  return s.replace(/_/g, ' ').replace(/\b\w/g, (c) => c.toUpperCase()).replace(/\bBy\b/, 'by');
}
