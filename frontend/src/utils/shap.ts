import type { ShapContribution } from '../types';

/** Splits already-computed Phase 3 contributions into risk drivers and protective factors. */
export function splitDrivers(contributions: ShapContribution[], limit = 3) {
  const positive = contributions
    .filter((c) => c.contribution > 0)
    .sort((a, b) => b.contribution - a.contribution)
    .slice(0, limit);
  const negative = contributions
    .filter((c) => c.contribution < 0)
    .sort((a, b) => a.contribution - b.contribution)
    .slice(0, limit);
  return { positive, negative };
}
