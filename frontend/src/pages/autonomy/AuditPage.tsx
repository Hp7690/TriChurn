import { useMemo, useState } from 'react';
import { AsyncBoundary } from '../../components/AsyncBoundary';
import { Card } from '../../components/Card';
import { LoadingSkeleton } from '../../components/LoadingSkeleton';
import { Pagination } from '../../components/Pagination';
import { labelise } from '../../components/autonomy/parts';
import { useAsync } from '../../hooks/useAsync';
import { useAutonomy } from '../../services/autonomy';
import type { AuditQuery } from '../../types/autonomy';

const EVENT_TYPES = ['recommendation_created', 'status_changed', 'authorization_denied', 'eligibility_failed', 'risk_scan', 'generation_run', 'feedback_recorded'];

export function AuditPage() {
  const service = useAutonomy();
  const [eventType, setEventType] = useState('');
  const [recommendationId, setRecommendationId] = useState('');
  const [page, setPage] = useState(1);
  const query = useMemo<AuditQuery>(
    () => ({ page, pageSize: 50, eventType: eventType || undefined, recommendationId: recommendationId.trim() || undefined }),
    [page, eventType, recommendationId],
  );
  const state = useAsync(() => service.getAudit(query), [service, query]);

  return (
    <div className="space-y-6">
      <Card description="Append-only: entries cannot be edited or deleted. Only customer IDs are stored, never contact details.">
        <div className="grid gap-3 sm:grid-cols-3">
          <div>
            <label htmlFor="au-type" className="field-label">Event type</label>
            <select id="au-type" className="field" value={eventType} onChange={(e) => { setEventType(e.target.value); setPage(1); }}>
              <option value="">All</option>
              {EVENT_TYPES.map((t) => <option key={t} value={t}>{labelise(t)}</option>)}
            </select>
          </div>
          <div>
            <label htmlFor="au-rec" className="field-label">Recommendation ID</label>
            <input id="au-rec" className="field" value={recommendationId} onChange={(e) => { setRecommendationId(e.target.value); setPage(1); }} />
          </div>
        </div>
      </Card>
      <AsyncBoundary state={state} skeleton={<LoadingSkeleton variant="table" rows={8} />} isEmpty={(p) => p.total === 0} emptyTitle="No audit events" emptyDescription="Events are recorded as recommendations are generated and as the workflow is used." errorTitle="Unable to load the audit trail.">
        {(p) => (
          <Card>
            <div className="overflow-x-auto rounded-lg border border-slate-200">
              <table className="w-full min-w-[900px] text-sm">
                <caption className="sr-only">Audit trail</caption>
                <thead className="bg-slate-50 text-xs text-slate-600"><tr>{['When', 'Event', 'Recommendation', 'Customer', 'Change', 'Actor', 'Detail'].map((h) => <th key={h} scope="col" className="px-3 py-2.5 text-left">{h}</th>)}</tr></thead>
                <tbody className="divide-y divide-slate-100">
                  {p.items.map((a) => (
                    <tr key={a.audit_id}>
                      <td className="px-3 py-2.5 text-xs">{a.created_at}</td>
                      <td className="px-3 py-2.5 capitalize">{labelise(a.event_type)}</td>
                      <td className="px-3 py-2.5 text-xs">{a.recommendation_id ?? '—'}</td>
                      <td className="px-3 py-2.5">{a.customer_id ?? '—'}</td>
                      <td className="px-3 py-2.5">{a.from_status || a.to_status ? `${a.from_status ?? '—'} → ${a.to_status ?? '—'}` : '—'}</td>
                      <td className="px-3 py-2.5">{a.actor}{!a.actor_authenticated && <span className="ml-1 text-xs text-slate-500">(unauthenticated)</span>}</td>
                      <td className="max-w-xs px-3 py-2.5 text-xs text-slate-600">{a.detail}</td>
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
