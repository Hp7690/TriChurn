import { useMemo, useState } from 'react';
import { AsyncBoundary } from '../../components/AsyncBoundary';
import { Card } from '../../components/Card';
import { LoadingSkeleton } from '../../components/LoadingSkeleton';
import { Pagination } from '../../components/Pagination';
import { Notice, labelise } from '../../components/autonomy/parts';
import { useAsync } from '../../hooks/useAsync';
import { toError } from '../../services/api/errors';
import { useAutonomy } from '../../services/autonomy';
import type { RiskQuery } from '../../types/autonomy';
import { formatPercent } from '../../utils/format';

const select = 'field';

export function RiskMonitorPage() {
  const service = useAutonomy();
  const [riskLevel, setRiskLevel] = useState('');
  const [status, setStatus] = useState('');
  const [page, setPage] = useState(1);
  const [version, setVersion] = useState(0);
  const [message, setMessage] = useState<{ tone: 'ok' | 'error'; text: string } | null>(null);

  const query = useMemo<RiskQuery>(
    () => ({ page, pageSize: 25, riskLevel: riskLevel || undefined, status: (status || undefined) as RiskQuery['status'] }),
    [page, riskLevel, status],
  );
  const state = useAsync(() => service.getRisks(query), [service, query, version]);

  const scan = async () => {
    try {
      const r = await service.scanRisks();
      setMessage({ tone: 'ok', text: `Scan ${r.status}: ${r.events_created} new events, ${r.events_resolved} resolved. ${r.note}` });
      setVersion((v) => v + 1);
    } catch (e) {
      setMessage({ tone: 'error', text: toError(e).message });
    }
  };

  return (
    <div className="space-y-6">
      <Notice tone="info">
        This is <strong>batch</strong> monitoring: each scan stores a snapshot of the scored portfolio and compares it with the previous one. There is no live customer event stream, and the first scan is only a baseline.
      </Notice>
      <Card>
        <div className="grid gap-3 sm:grid-cols-4">
          <div>
            <label htmlFor="rk-level" className="field-label">Risk level</label>
            <select id="rk-level" className={select} value={riskLevel} onChange={(e) => { setRiskLevel(e.target.value); setPage(1); }}>
              <option value="">All</option>
              {['LOW', 'MEDIUM', 'HIGH', 'CRITICAL'].map((b) => <option key={b} value={b}>{b}</option>)}
            </select>
          </div>
          <div>
            <label htmlFor="rk-status" className="field-label">Event status</label>
            <select id="rk-status" className={select} value={status} onChange={(e) => { setStatus(e.target.value); setPage(1); }}>
              <option value="">All</option>
              <option value="new">New</option>
              <option value="resolved">Resolved</option>
            </select>
          </div>
          <div className="flex items-end">
            <button type="button" onClick={() => void scan()} className="btn btn-primary">Run batch risk scan</button>
          </div>
        </div>
        {message && <div className="mt-3"><Notice tone={message.tone}>{message.text}</Notice></div>}
      </Card>
      <AsyncBoundary
        state={state}
        skeleton={<LoadingSkeleton variant="table" />}
        isEmpty={(p) => p.total === 0}
        emptyTitle="No risk events"
        emptyDescription="Events appear only after a later scan finds a change from the previous snapshot. With a static dataset this is expected."
        errorTitle="Unable to load risk events."
      >
        {(p) => (
          <Card>
            <div className="overflow-x-auto rounded-lg border border-slate-200">
              <table className="w-full min-w-[820px] text-sm">
                <caption className="sr-only">Risk events</caption>
                <thead className="bg-slate-50 text-xs text-slate-600">
                  <tr>
                    {['Detected', 'Customer', 'Event', 'From → To', 'Probability', 'Status', 'Source'].map((h) => <th key={h} scope="col" className="px-3 py-2.5 text-left">{h}</th>)}
                  </tr>
                </thead>
                <tbody className="divide-y divide-slate-100">
                  {p.items.map((e) => (
                    <tr key={e.event_id}>
                      <td className="px-3 py-2.5">{e.detected_at}</td>
                      <td className="px-3 py-2.5 font-medium">{e.customer_id}</td>
                      <td className="px-3 py-2.5 capitalize">{labelise(e.event_type)}</td>
                      <td className="px-3 py-2.5">{e.from_band ?? '—'} → {e.to_band}</td>
                      <td className="px-3 py-2.5 tabular-nums">{e.probability_before === null ? '—' : formatPercent(e.probability_before)} → {formatPercent(e.probability_after)}</td>
                      <td className="px-3 py-2.5 capitalize">{e.status}</td>
                      <td className="px-3 py-2.5 text-xs text-slate-500">{labelise(e.source)}</td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
            <Pagination page={p.page} pageCount={p.page_count} total={p.total} pageSize={p.page_size} onPageChange={setPage} />
          </Card>
        )}
      </AsyncBoundary>
    </div>
  );
}
