import type { RiskBand } from '../types';
import { cn } from '../utils/cn';
import { RISK_BADGE_CLASSES, RISK_COLORS } from '../utils/theme';

export function RiskBadge({ band }: { band: RiskBand }) {
  return (
    <span
      className={cn(
        'inline-flex items-center gap-1.5 rounded-full px-2.5 py-0.5 text-xs font-medium ring-1 ring-inset',
        RISK_BADGE_CLASSES[band],
      )}
    >
      <span className="h-1.5 w-1.5 rounded-full" style={{ backgroundColor: RISK_COLORS[band] }} aria-hidden="true" />
      <span>{band}</span>
    </span>
  );
}
