import { useState, type ReactNode } from 'react';
import type { EvidenceStatus, Metric } from '../../types/revenue';
import { formatMetricValue, isNullStatus } from './format';
import type { AsyncState } from './useAsync';

const cx = (...c: Array<string | false | null | undefined>) => c.filter(Boolean).join(' ');

export const STATUS_TEXT: Record<EvidenceStatus, string> = {
  ACTUAL: 'Actual',
  ESTIMATED: 'Estimated',
  PROXY: 'Proxy',
  ILLUSTRATIVE: 'Illustrative',
  UNAVAILABLE: 'Unavailable',
  BLOCKED_BY_MISSING_DATA: 'Blocked: missing data',
};
const STATUS_CLASS: Record<EvidenceStatus, string> = {
  ACTUAL: 'bg-emerald-50 text-emerald-800 ring-emerald-600/20',
  ESTIMATED: 'bg-indigo-50 text-indigo-800 ring-indigo-600/20',
  PROXY: 'bg-amber-50 text-amber-900 ring-amber-600/30',
  ILLUSTRATIVE: 'bg-fuchsia-50 text-fuchsia-800 ring-fuchsia-600/20',
  UNAVAILABLE: 'bg-slate-100 text-slate-700 ring-slate-500/20',
  BLOCKED_BY_MISSING_DATA: 'bg-rose-50 text-rose-800 ring-rose-600/20',
};

export function StatusBadge({ status }: { status: EvidenceStatus }) {
  return (
    <span
      data-testid="status-badge"
      data-status={status}
      title={STATUS_TEXT[status]}
      className={cx('inline-flex items-center rounded-md px-2 py-0.5 text-xs font-semibold ring-1 ring-inset', STATUS_CLASS[status])}
    >
      {STATUS_TEXT[status]}
    </span>
  );
}

export function Panel({ title, subtitle, badge, children }: { title: string; subtitle?: string; badge?: ReactNode; children: ReactNode }) {
  return (
    <section aria-label={title} className="rounded-xl border border-slate-200 bg-surface p-5 shadow-sm">
      <header className="mb-3 flex flex-wrap items-start justify-between gap-2">
        <div>
          <h2 className="text-base font-semibold text-slate-900">{title}</h2>
          {subtitle ? <p className="mt-0.5 text-sm text-slate-600">{subtitle}</p> : null}
        </div>
        {badge}
      </header>
      {children}
    </section>
  );
}

export function Notice({ tone, children }: { tone: 'info' | 'warn' | 'error' | 'ok'; children: ReactNode }) {
  const classes = { info: 'bg-slate-100 text-slate-800', warn: 'bg-amber-50 text-amber-900', error: 'bg-rose-50 text-rose-800', ok: 'bg-emerald-50 text-emerald-800' }[tone];
  return (
    <p role={tone === 'error' ? 'alert' : 'status'} className={cx('rounded-lg px-4 py-2 text-sm', classes)}>
      {children}
    </p>
  );
}

export function EmptyState({ title, children }: { title: string; children?: ReactNode }) {
  return (
    <div role="note" className="rounded-lg border border-dashed border-slate-300 bg-slate-50 px-4 py-6 text-center">
      <p className="text-sm font-semibold text-slate-800">{title}</p>
      {children ? <div className="mt-1 text-sm text-slate-600">{children}</div> : null}
    </div>
  );
}

/** Metric details: formula, source fields, assumptions, limitations, timestamp. Shown on the dashboard, not only in docs. */
export function MetricDetails({ metric }: { metric: Metric }) {
  const [open, setOpen] = useState(false);
  return (
    <div className="mt-2 text-xs">
      <button
        type="button"
        aria-expanded={open}
        onClick={() => setOpen((o) => !o)}
        className="font-medium text-brand-700 underline-offset-2 hover:underline"
      >
        {open ? 'Hide definition' : 'Formula & assumptions'}
      </button>
      {open ? (
        <dl className="mt-2 space-y-1 rounded-md bg-slate-50 p-2 text-slate-700" data-testid={`details-${metric.key}`}>
          <dt className="font-semibold">Formula</dt>
          <dd>{metric.formula}</dd>
          <dt className="font-semibold">Source fields</dt>
          <dd>{metric.source_fields.join(', ')}</dd>
          {metric.assumptions.length ? (
            <>
              <dt className="font-semibold">Assumptions</dt>
              <dd><ul className="list-disc pl-4">{metric.assumptions.map((a) => <li key={a}>{a}</li>)}</ul></dd>
            </>
          ) : null}
          {metric.limitations.length ? (
            <>
              <dt className="font-semibold">Limitations</dt>
              <dd><ul className="list-disc pl-4">{metric.limitations.map((a) => <li key={a}>{a}</li>)}</ul></dd>
            </>
          ) : null}
          <dt className="font-semibold">Calculated</dt>
          <dd>{metric.calculated_at}</dd>
        </dl>
      ) : null}
    </div>
  );
}

export function KpiCard({ metric, label }: { metric: Metric; label?: string }) {
  const unavailable = isNullStatus(metric.status) || metric.value === null;
  return (
    <article aria-label={label ?? metric.name} className="rounded-xl border border-slate-200 bg-surface p-4 shadow-sm" data-testid={`kpi-${metric.key}`}>
      <div className="flex items-start justify-between gap-2">
        <h3 className="text-sm font-medium text-slate-600">{label ?? metric.name}</h3>
        <StatusBadge status={metric.status} />
      </div>
      <p className={cx('mt-2 text-2xl font-bold', unavailable ? 'text-slate-400' : 'text-slate-900')} data-testid="kpi-value">
        {formatMetricValue(metric)}
      </p>
      {unavailable && metric.reason ? <p className="mt-1 text-xs text-slate-600">{metric.reason}</p> : null}
      <MetricDetails metric={metric} />
    </article>
  );
}

export function LoadingState({ label = 'Loading' }: { label?: string }) {
  return (
    <div role="status" aria-live="polite" className="animate-pulse rounded-lg bg-slate-100 px-4 py-8 text-center text-sm text-slate-600">
      {label}…
    </div>
  );
}

export function ErrorState({ error, onRetry }: { error: Error; onRetry?: () => void }) {
  return (
    <div role="alert" className="rounded-lg border border-rose-200 bg-rose-50 px-4 py-4 text-sm text-rose-900">
      <p className="font-semibold">This section could not be loaded.</p>
      <p className="mt-1">{error.message}</p>
      {onRetry ? (
        <button type="button" onClick={onRetry} className="btn btn-danger btn-sm mt-2">
          Retry
        </button>
      ) : null}
    </div>
  );
}

/** Loading / error / content boundary for an async hook result. */
export function AsyncView<T>({ state, label, children }: { state: AsyncState<T>; label?: string; children: (data: T) => ReactNode }) {
  if (state.loading && !state.data) return <LoadingState label={label} />;
  if (state.error) return <ErrorState error={state.error} onRetry={state.reload} />;
  if (!state.data) return <EmptyState title="No data returned" />;
  return <>{children(state.data)}</>;
}

export function Pagination({ page, pageCount, total, onPage }: { page: number; pageCount: number; total: number; onPage: (p: number) => void }) {
  return (
    <nav aria-label="Pagination" className="mt-3 flex items-center justify-between text-sm text-slate-700">
      <span>{total.toLocaleString('en-US')} rows · page {page} of {pageCount}</span>
      <span className="flex gap-2">
        <button type="button" disabled={page <= 1} onClick={() => onPage(page - 1)} className="btn btn-secondary btn-sm">Previous</button>
        <button type="button" disabled={page >= pageCount} onClick={() => onPage(page + 1)} className="btn btn-secondary btn-sm">Next</button>
      </span>
    </nav>
  );
}

export interface Column<T> {
  key: string;
  header: string;
  render: (row: T) => ReactNode;
  align?: 'right';
}

export function DataTable<T>({ rows, columns, rowKey, caption, empty }: { rows: T[]; columns: Column<T>[]; rowKey: (r: T) => string; caption: string; empty?: ReactNode }) {
  if (rows.length === 0) return <>{empty ?? <EmptyState title="No rows match." />}</>;
  return (
    <div className="overflow-x-auto">
      <table className="min-w-full text-left text-sm">
        <caption className="sr-only">{caption}</caption>
        <thead className="border-b border-slate-200 text-xs text-slate-500">
          <tr>{columns.map((c) => <th key={c.key} scope="col" className={cx('px-3 py-2 font-semibold', c.align === 'right' && 'text-right')}>{c.header}</th>)}</tr>
        </thead>
        <tbody className="divide-y divide-slate-100">
          {rows.map((r) => (
            <tr key={rowKey(r)}>
              {columns.map((c) => <td key={c.key} className={cx('px-3 py-2 text-slate-800', c.align === 'right' && 'text-right tabular-nums')}>{c.render(r)}</td>)}
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}

export function PageIntro({ title, description }: { title: string; description: string }) {
  return (
    <div className="mb-4">
      <h1 className="text-xl font-bold text-slate-900">{title}</h1>
      <p className="mt-1 text-sm text-slate-600">{description}</p>
    </div>
  );
}

export function WarningList({ items }: { items: string[] }) {
  if (!items.length) return null;
  return <div className="space-y-2">{items.map((w) => <Notice key={w} tone="warn">{w}</Notice>)}</div>;
}
