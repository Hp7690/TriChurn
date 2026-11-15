import type { ReactNode } from 'react';
import { Drawer } from '../Drawer';
import type { WorkflowStatus } from '../../types/autonomy';
import { cn } from '../../utils/cn';

const STATUS_CLASSES: Record<WorkflowStatus, string> = {
  pending: 'bg-amber-50 text-amber-800 ring-amber-600/20',
  approved: 'bg-indigo-50 text-indigo-800 ring-indigo-600/20',
  rejected: 'bg-rose-50 text-rose-800 ring-rose-600/20',
  executed: 'bg-emerald-50 text-emerald-800 ring-emerald-600/20',
  failed: 'bg-rose-100 text-rose-900 ring-rose-700/20',
  cancelled: 'bg-slate-100 text-slate-700 ring-slate-500/20',
};

export function WorkflowStatusBadge({ status }: { status: WorkflowStatus }) {
  return (
    <span className={cn('inline-flex items-center rounded-md px-2 py-0.5 text-xs font-semibold capitalize ring-1 ring-inset', STATUS_CLASSES[status])}>
      {status}
    </span>
  );
}

export function Notice({ tone, children }: { tone: 'info' | 'warn' | 'error' | 'ok'; children: ReactNode }) {
  const classes = {
    info: 'bg-slate-100 text-slate-800',
    warn: 'bg-amber-50 text-amber-900',
    error: 'bg-rose-50 text-rose-800',
    ok: 'bg-emerald-50 text-emerald-800',
  }[tone];
  return (
    <p role={tone === 'error' ? 'alert' : 'status'} className={cn('rounded-lg px-4 py-2 text-sm', classes)}>
      {children}
    </p>
  );
}

interface ConfirmProps {
  open: boolean;
  title: string;
  description: string;
  confirmLabel: string;
  busy?: boolean;
  onConfirm: (note: string) => void;
  onCancel: () => void;
  withNote?: boolean;
}

/** Confirmation panel for consequential actions (built on the existing Drawer). */
export function ConfirmPanel({ open, title, description, confirmLabel, busy, onConfirm, onCancel, withNote = true }: ConfirmProps) {
  return (
    <Drawer open={open} onClose={onCancel} title={title}>
      <form
        className="space-y-4 p-4"
        onSubmit={(event) => {
          event.preventDefault();
          const data = new FormData(event.currentTarget);
          onConfirm(String(data.get('note') ?? ''));
        }}
      >
        <p className="text-sm text-slate-700">{description}</p>
        {withNote && (
          <div>
            <label htmlFor="confirm-note" className="field-label">Note (optional, max 200 characters; do not enter personal data)</label>
            <textarea id="confirm-note" name="note" rows={3} maxLength={200} className="field" />
          </div>
        )}
        <div className="flex gap-2">
          <button type="submit" disabled={busy} className="btn btn-primary">
            {busy ? 'Working…' : confirmLabel}
          </button>
          <button type="button" onClick={onCancel} className="btn btn-secondary">Cancel</button>
        </div>
      </form>
    </Drawer>
  );
}

export const labelise = (value: string): string => value.replace(/_/g, ' ');

const PRIORITY_CLASSES: Record<string, string> = {
  high: 'bg-rose-50 text-rose-800 ring-rose-600/20',
  medium: 'bg-amber-50 text-amber-800 ring-amber-600/20',
  low: 'bg-slate-100 text-slate-700 ring-slate-500/20',
};

/** Autonomy priorities are high / medium / low (not the retention P1 / P2 tiers). Unknown values stay neutral. */
export function PriorityBadge({ priority }: { priority: string }) {
  return (
    <span
      className={cn(
        'inline-flex items-center rounded-md px-2 py-0.5 text-xs font-semibold capitalize ring-1 ring-inset',
        PRIORITY_CLASSES[priority.toLowerCase()] ?? 'bg-slate-100 text-slate-700 ring-slate-500/20',
      )}
    >
      {priority}
    </span>
  );
}
