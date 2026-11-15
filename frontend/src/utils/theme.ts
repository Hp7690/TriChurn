import type { RiskBand, SegmentId } from '../types';

export const RISK_BANDS: readonly RiskBand[] = ['Low', 'Medium', 'High'];

/** Chart colours (hex) — kept in one place so every chart agrees. */
export const RISK_COLORS: Record<RiskBand, string> = {
  Low: '#059669',
  Medium: '#d97706',
  High: '#e11d48',
};

export const SEGMENT_COLORS: Record<SegmentId, string> = {
  'low-value-high-risk': '#e11d48',
  'high-value-stable': '#5869e8',
  'low-value-stable': '#0d9488',
};

export const RISK_BADGE_CLASSES: Record<RiskBand, string> = {
  Low: 'bg-emerald-50 text-emerald-800 ring-emerald-600/20',
  Medium: 'bg-amber-50 text-amber-800 ring-amber-600/20',
  High: 'bg-rose-50 text-rose-800 ring-rose-600/20',
};

export const SEGMENT_BADGE_CLASSES: Record<SegmentId, string> = {
  'low-value-high-risk': 'bg-rose-50 text-rose-800 ring-rose-600/20',
  'high-value-stable': 'bg-brand-50 text-brand-700 ring-brand-600/20',
  'low-value-stable': 'bg-teal-50 text-teal-800 ring-teal-600/20',
};

export const POSITIVE_SHAP_COLOR = '#e11d48';
export const NEGATIVE_SHAP_COLOR = '#059669';
