/** Currency-aware formatting for Phase 9 (Phase 4 reports INR; the dashboard `formatCurrency` helper in utils/format is USD-only). */
export function formatMoney(value: number, currencyCode = 'INR'): string {
  try {
    return new Intl.NumberFormat(currencyCode === 'INR' ? 'en-IN' : 'en-US', {
      style: 'currency',
      currency: currencyCode,
      maximumFractionDigits: 0,
    }).format(value);
  } catch {
    return `${currencyCode} ${Math.round(value).toLocaleString('en-US')}`;
  }
}

export function formatCompactMoney(value: number, currencyCode = 'INR'): string {
  try {
    return new Intl.NumberFormat(currencyCode === 'INR' ? 'en-IN' : 'en-US', {
      style: 'currency',
      currency: currencyCode,
      notation: 'compact',
      maximumFractionDigits: 1,
    }).format(value);
  } catch {
    return `${currencyCode} ${Math.round(value).toLocaleString('en-US')}`;
  }
}

export const formatRatio = (value: number | null): string => (value === null ? '—' : `${(value * 100).toFixed(0)}%`);
