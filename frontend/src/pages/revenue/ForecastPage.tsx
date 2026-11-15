import { useState } from 'react';
import { formatNumber } from '../../components/revenue/format';
import { AsyncView, DataTable, ErrorState, KpiCard, LoadingState, Notice, PageIntro, Panel, StatusBadge } from '../../components/revenue/primitives';
import { useAsync } from '../../components/revenue/useAsync';
import { useRevenue } from '../../services/revenue';
import type { ForecastReadiness, ForecastRowInput } from '../../types/revenue';

const MAX_CHARS = 2_000_000;
const MAX_ROWS = 50_000;

/** Minimal CSV parser for pasted history (header: period,customer_id,revenue[,product,segment]). Not for quoted fields. */
export function parseHistoryCsv(text: string): { rows: ForecastRowInput[]; error?: string } {
  if (text.length > MAX_CHARS) return { rows: [], error: 'Input is too large (limit 2 MB).' };
  const lines = text.split(/\r?\n/).filter((l) => l.trim() !== '');
  if (lines.length < 2) return { rows: [], error: 'Paste a header row and at least one data row.' };
  const header = (lines[0] ?? '').split(',').map((h) => h.trim());
  for (const need of ['period', 'customer_id', 'revenue'])
    if (!header.includes(need)) return { rows: [], error: `Missing required column: ${need}.` };
  if (lines.length - 1 > MAX_ROWS) return { rows: [], error: `Too many rows (limit ${MAX_ROWS}).` };
  const rows = lines.slice(1).map((line) => {
    const cells = line.split(',').map((c) => c.trim());
    const get = (k: string) => cells[header.indexOf(k)] ?? '';
    const row: ForecastRowInput = { period: get('period'), customer_id: get('customer_id'), revenue: get('revenue') === '' ? null : get('revenue') };
    if (header.includes('product') && get('product')) row.product = get('product');
    if (header.includes('segment') && get('segment')) row.segment = get('segment');
    return row;
  });
  return { rows };
}

function ReadinessReport({ r, title }: { r: ForecastReadiness; title: string }) {
  const ready = r.state === 'FORECAST_READY';
  const rd = r.readiness;
  return (
    <Panel title={title} badge={<StatusBadge status={ready ? 'ACTUAL' : 'BLOCKED_BY_MISSING_DATA'} />}>
      <p className="font-mono text-sm font-semibold" data-testid="forecast-state">{r.state}</p>
      <ul className="mt-2 list-disc pl-5 text-sm text-slate-700">{rd.reasons.map((x) => <li key={x}>{x}</li>)}</ul>
      <dl className="mt-3 grid grid-cols-2 gap-2 text-sm sm:grid-cols-4">
        {[['Rows received', rd.rows_received], ['Valid rows', rd.rows_valid], ['Periods observed', rd.periods_observed], ['Periods required', rd.min_periods_required],
          ['Invalid dates', rd.invalid_dates], ['Invalid revenue', rd.invalid_revenue + rd.negative_revenue], ['Duplicate rows', rd.duplicate_rows], ['Missing periods', rd.missing_periods.length]].map(([k, v]) => (
          <div key={String(k)}><dt className="text-xs text-slate-500">{k}</dt><dd className="font-semibold">{formatNumber(Number(v))}</dd></div>
        ))}
      </dl>
      {rd.first_period ? <p className="mt-2 text-xs text-slate-600">Span: {rd.first_period} to {rd.last_period}</p> : null}
      {r.backtest ? (
        <div className="mt-3 rounded-md bg-slate-50 p-3 text-sm" data-testid="backtest">
          <p className="font-semibold">Baseline backtest: {r.backtest.status}</p>
          {r.backtest.reason ? <p>{r.backtest.reason}</p> : null}
          {r.backtest.results?.map((x) => <p key={x.model}>{x.model}: MAE {x.mae}{x.mape !== null ? `, MAPE ${(x.mape * 100).toFixed(1)}%` : ''}</p>)}
          {r.backtest.note ? <p className="text-xs text-slate-600">{r.backtest.note}</p> : null}
        </div>
      ) : null}
      <p className="mt-3 text-xs text-slate-600">{r.note}</p>
    </Panel>
  );
}

export function ForecastPage() {
  const api = useRevenue();
  const readiness = useAsync(() => api.forecastReadiness(), [api]);
  const [text, setText] = useState('');
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<Error | null>(null);
  const [parseError, setParseError] = useState<string | null>(null);
  const [result, setResult] = useState<ForecastReadiness | null>(null);

  async function validate(backtest: boolean) {
    setParseError(null);
    setError(null);
    const parsed = parseHistoryCsv(text);
    if (parsed.error) {
      setParseError(parsed.error);
      return;
    }
    setBusy(true);
    try {
      setResult(await api.forecastValidate(parsed.rows, backtest));
    } catch (e) {
      setError(e instanceof Error ? e : new Error(String(e)));
    } finally {
      setBusy(false);
    }
  }

  return (
    <div className="space-y-6">
      <PageIntro title="Revenue Forecasting" description="A forecasting foundation. Without real, time-indexed revenue history no model is trained and no forecast is produced." />
      <AsyncView state={readiness} label="Loading forecast readiness">
        {(r) => (
          <>
            {r.state !== 'FORECAST_READY' ? (
              <Notice tone="warn">Forecasting is blocked: {r.readiness.reasons.join(' ')} No forecast, projection or trend line is shown because it could not be validated.</Notice>
            ) : null}
            <div className="grid gap-4 sm:grid-cols-2">{r.metrics.map((m) => <KpiCard key={m.key} metric={m} />)}</div>
            <ReadinessReport r={r} title="Readiness of the configured history" />
            <Panel title="Requirements" subtitle="Minimum history and validation rules.">
              <ul className="list-disc pl-5 text-sm text-slate-700">
                <li>Fields: {Object.entries(r.schema.required).map(([k, v]) => `${k} (${v})`).join('; ')}</li>
                <li>Optional: {Object.keys(r.schema.optional).join(', ')}</li>
                <li>At least {String(r.requirements.min_periods)} contiguous {String(r.requirements.frequency)} periods; at most {Math.round(Number(r.requirements.max_missing_period_share) * 100)}% missing periods.</li>
                <li>No duplicate customer/period rows, no invalid dates, no negative revenue.</li>
              </ul>
              <DataTable caption="Schema" rows={Object.entries(r.schema.required)} rowKey={([k]) => k} columns={[{ key: 'k', header: 'Required field', render: ([k]) => k }, { key: 'v', header: 'Format', render: ([, v]) => v }]} />
            </Panel>
          </>
        )}
      </AsyncView>
      <Panel title="Validate your own history" subtitle="Paste CSV with header period,customer_id,revenue. Sent only to this TriChurn API; validation only, no forecast is produced.">
        <label className="block text-sm font-medium" htmlFor="history-csv">Revenue history (CSV)</label>
        <textarea id="history-csv" value={text} onChange={(e) => setText(e.target.value)} rows={6} className="mt-1 w-full rounded-md border border-slate-300 p-2 font-mono text-xs" placeholder="period,customer_id,revenue&#10;2023-01,C1,100" />
        <div className="mt-2 flex gap-2">
          <button type="button" disabled={busy} onClick={() => void validate(false)} className="btn btn-primary btn-sm">Validate</button>
          <button type="button" disabled={busy} onClick={() => void validate(true)} className="btn btn-secondary btn-sm">Validate + baseline backtest</button>
        </div>
        {parseError ? <div className="mt-2"><Notice tone="error">{parseError}</Notice></div> : null}
        {busy ? <div className="mt-2"><LoadingState label="Validating" /></div> : null}
        {error ? <div className="mt-2"><ErrorState error={error} /></div> : null}
      </Panel>
      {result ? <ReadinessReport r={result} title="Validation result" /> : null}
    </div>
  );
}
