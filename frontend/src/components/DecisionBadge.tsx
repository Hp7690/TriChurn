import type { InterventionDecision } from '../types';
import { cn } from '../utils/cn';

export function DecisionBadge({ decision }: { decision: InterventionDecision }) {
  const intervene = decision === 'Intervene';
  return (
    <span
      className={cn(
        'inline-flex items-center whitespace-nowrap rounded-md px-2 py-0.5 text-xs font-semibold ring-1 ring-inset',
        intervene ? 'bg-brand-50 text-brand-800 ring-brand-600/20' : 'bg-slate-100 text-slate-700 ring-slate-500/20',
      )}
    >
      {decision}
    </span>
  );
}
