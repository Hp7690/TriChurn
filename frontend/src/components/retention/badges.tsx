import type { PriorityTier } from '../../types/retention';
import { cn } from '../../utils/cn';

const TIER_CLASSES: Record<PriorityTier, string> = {
  P1: 'bg-rose-50 text-rose-800 ring-rose-600/20',
  P2: 'bg-orange-50 text-orange-800 ring-orange-600/20',
  P3: 'bg-amber-50 text-amber-800 ring-amber-600/20',
  P4: 'bg-slate-100 text-slate-700 ring-slate-500/20',
  MONITOR: 'bg-slate-50 text-slate-600 ring-slate-400/20',
};

export function TierBadge({ tier }: { tier: PriorityTier }) {
  return (
    <span className={cn('inline-flex items-center rounded-md px-2 py-0.5 text-xs font-semibold ring-1 ring-inset', TIER_CLASSES[tier])}>
      {tier === 'MONITOR' ? 'Monitor' : tier}
    </span>
  );
}

/** Marks figures that come from assumptions rather than measured outcomes. */
export function EstimateBadge({ children = 'ESTIMATE' }: { children?: string }) {
  return (
    <span className="inline-flex items-center rounded-full bg-amber-100 px-2 py-0.5 text-[11px] font-semibold text-amber-900">
      {children}
    </span>
  );
}

export function ObservedBadge() {
  return (
    <span className="inline-flex items-center rounded-full bg-emerald-100 px-2 py-0.5 text-[11px] font-semibold text-emerald-900">
      Recorded
    </span>
  );
}
