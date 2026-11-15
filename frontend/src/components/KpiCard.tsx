import type { LucideIcon } from 'lucide-react';
import { cn } from '../utils/cn';

export type KpiTone = 'default' | 'danger' | 'success' | 'brand';

const TONES: Record<KpiTone, string> = {
  default: 'bg-slate-100 text-slate-600',
  danger: 'bg-rose-50 text-rose-600',
  success: 'bg-emerald-50 text-emerald-600',
  brand: 'bg-brand-50 text-brand-600',
};

interface KpiCardProps {
  label: string;
  value: string;
  hint?: string;
  icon: LucideIcon;
  tone?: KpiTone;
}

export function KpiCard({ label, value, hint, icon: Icon, tone = 'default' }: KpiCardProps) {
  return (
    <section aria-label={label} className="rounded-xl border border-slate-200 bg-surface p-5 shadow-sm">
      <div className="flex items-center justify-between gap-3">
        <p className="text-sm font-medium text-slate-600">{label}</p>
        <span className={cn('grid h-8 w-8 shrink-0 place-items-center rounded-lg', TONES[tone])} aria-hidden="true">
          <Icon className="h-[18px] w-[18px]" />
        </span>
      </div>
      <p className="mt-3 truncate text-[28px] font-semibold leading-none tracking-tight tabular-nums text-slate-900">{value}</p>
      {hint && <p className="mt-2.5 text-xs leading-5 text-slate-500">{hint}</p>}
    </section>
  );
}
