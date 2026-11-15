import { AlertOctagon, CheckCircle2, CircleDashed, CircleSlash, Hourglass } from 'lucide-react';
import type { ModuleStatus } from '../types/experience';
import { cn } from '../utils/cn';

const STATUS_META: Record<ModuleStatus, { label: string; classes: string; icon: typeof CheckCircle2 }> = {
  AVAILABLE: { label: 'Available', classes: 'bg-emerald-100 text-emerald-800', icon: CheckCircle2 },
  PARTIALLY_AVAILABLE: { label: 'Partially available', classes: 'bg-amber-100 text-amber-900', icon: Hourglass },
  BLOCKED_BY_MISSING_DATA: { label: 'Blocked by missing data', classes: 'bg-slate-200 text-slate-800', icon: CircleSlash },
  DISABLED: { label: 'Disabled', classes: 'bg-slate-100 text-slate-600', icon: CircleDashed },
  VALIDATION_FAILED: { label: 'Validation failed', classes: 'bg-rose-100 text-rose-800', icon: AlertOctagon },
};

export const STATUS_ORDER: ModuleStatus[] = [
  'AVAILABLE',
  'PARTIALLY_AVAILABLE',
  'BLOCKED_BY_MISSING_DATA',
  'DISABLED',
  'VALIDATION_FAILED',
];

export function statusLabel(status: ModuleStatus): string {
  return STATUS_META[status].label;
}

/** Status is shown as icon + text + colour, never colour alone. The raw code is kept in `data-status` for tests. */
export function ExperienceStatusBadge({ status }: { status: ModuleStatus }) {
  const { label, classes, icon: Icon } = STATUS_META[status];
  return (
    <span
      data-status={status}
      className={cn('inline-flex items-center gap-1.5 rounded-full px-2.5 py-1 text-xs font-semibold', classes)}
    >
      <Icon className="h-3.5 w-3.5" aria-hidden="true" />
      {label}
    </span>
  );
}
