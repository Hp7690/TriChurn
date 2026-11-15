export const formatCurrency = (
  value: number,
  currencyCode = 'USD',
  maximumFractionDigits = 0,
): string =>
  new Intl.NumberFormat('en-US', {
    style: 'currency',
    currency: currencyCode,
    minimumFractionDigits: maximumFractionDigits,
    maximumFractionDigits,
  }).format(value);

export const formatCompactCurrency = (
  value: number,
  currencyCode = 'USD',
): string =>
  new Intl.NumberFormat('en-US', {
    style: 'currency',
    currency: currencyCode,
    notation: 'compact',
    maximumFractionDigits: 1,
  }).format(value);

const integer = new Intl.NumberFormat('en-US');
export const formatNumber = (value: number): string => integer.format(value);
/** `fraction` is 0–1. */
export const formatPercent = (fraction: number, digits = 1): string => `${(fraction * 100).toFixed(digits)}%`;
export const formatSigned = (value: number, digits = 3): string =>
  `${value > 0 ? '+' : ''}${value.toFixed(digits)}`;
export const formatMetric = (value: number): string => value.toFixed(4);
