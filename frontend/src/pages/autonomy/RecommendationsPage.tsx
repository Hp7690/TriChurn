import { useMemo, useState } from 'react';
import { AsyncBoundary } from '../../components/AsyncBoundary';
import { Card } from '../../components/Card';
import { LoadingSkeleton } from '../../components/LoadingSkeleton';
import { Pagination } from '../../components/Pagination';
import { PriorityBadge, WorkflowStatusBadge, labelise } from '../../components/autonomy/parts';
import { useAsync } from '../../hooks/useAsync';
import { useAutonomy } from '../../services/autonomy';
import type { AutonomyRecommendation, RecommendationQuery, WorkflowStatus } from '../../types/autonomy';
import { formatPercent } from '../../utils/format';

const select = 'field';
const STATUSES: WorkflowStatus[] = ['pending', 'approved', 'rejected', 'executed', 'failed', 'cancelled'];
const CATEGORIES = ['personalized_offer', 'customer_support_followup', 'subscription_review', 'retention_campaign_enrollment'];

function Evidence({ rec }: { rec: AutonomyRecommendation }) {
  const phase4 = rec.evidence.phase4 as { estimated_net_benefit?: number; assumed_success_rate?: number } | undefined;
  return (
    <details>
      <summary className="cursor-pointer text-brand-700">Evidence</summary>
      <dl className="mt-1 max-w-sm space-y-1 text-xs text-slate-700">
        <div><dt className="inline font-medium">Source:</dt> <dd className="inline">{labelise(rec.source)}</dd></div>
        <div><dt className="inline font-medium">Rule:</dt> <dd className="inline">{rec.rule_id} ({rec.rules_version})</dd></div>
        <div><dt className="inline font-medium">Churn probability:</dt> <dd className="inline">{formatPercent(rec.churn_probability)} (model output, not response likelihood)</dd></div>
        {phase4 && <div><dt className="inline font-medium">Estimated net benefit:</dt> <dd className="inline">{phase4.estimated_net_benefit} <span className="rounded bg-amber-100 px-1 font-semibold text-amber-900">ESTIMATE</span> at an assumed {Math.round((phase4.assumed_success_rate ?? 0) * 100)}% success rate</dd></div>}
        <div><dt className="inline font-medium">Confidence:</dt> <dd className="inline">{rec.confidence === null ? 'not provided (no calibrated evidence)' : rec.confidence}</dd></div>
      </dl>
    </details>
  );
}

export function RecommendationsPage() {
  const service = useAutonomy();
  const [status, setStatus] = useState('');
  const [category, setCategory] = useState('');
  const [priority, setPriority] = useState('');
  const [page, setPage] = useState(1);
  const query = useMemo<RecommendationQuery>(
    () => ({ page, pageSize: 25, status: (status || undefined) as WorkflowStatus | undefined, category: category || undefined, priority: priority || undefined }),
    [page, status, category, priority],
  );
  const state = useAsync(() => service.getRecommendations(query), [service, query]);
  const reset = (fn: () => void) => { fn(); setPage(1); };

  return (
    <div className="space-y-6">
      <Card>
        <div className="grid gap-3 sm:grid-cols-4">
          <div><label htmlFor="rc-status" className="field-label">Status</label>
            <select id="rc-status" className={select} value={status} onChange={(e) => reset(() => setStatus(e.target.value))}><option value="">All</option>{STATUSES.map((s) => <option key={s} value={s}>{s}</option>)}</select></div>
          <div><label htmlFor="rc-category" className="field-label">Category</label>
            <select id="rc-category" className={select} value={category} onChange={(e) => reset(() => setCategory(e.target.value))}><option value="">All</option>{CATEGORIES.map((c) => <option key={c} value={c}>{labelise(c)}</option>)}</select></div>
          <div><label htmlFor="rc-priority" className="field-label">Priority</label>
            <select id="rc-priority" className={select} value={priority} onChange={(e) => reset(() => setPriority(e.target.value))}><option value="">All</option>{['P1', 'P2', 'P3', 'P4'].map((p) => <option key={p} value={p}>{p}</option>)}</select></div>
        </div>
      </Card>
      <AsyncBoundary
        state={state}
        skeleton={<LoadingSkeleton variant="table" />}
        isEmpty={(p) => p.total === 0}
        emptyTitle="No recommendations yet"
        emptyDescription="Use “Generate recommendations” in the Command Center. Nothing is created automatically or invented."
        errorTitle="Unable to load recommendations."
      >
        {(p) => (
          <Card>
            <div className="overflow-x-auto rounded-lg border border-slate-200">
              <table className="w-full min-w-[1000px] text-sm">
                <caption className="sr-only">Recommendations</caption>
                <thead className="bg-slate-50 text-xs text-slate-600">
                  <tr>{['Customer', 'Recommendation', 'Why', 'Risk', 'Priority', 'Status', 'Created', 'Evidence'].map((h) => <th key={h} scope="col" className="px-3 py-2.5 text-left">{h}</th>)}</tr>
                </thead>
                <tbody className="divide-y divide-slate-100 align-top">
                  {p.items.map((r) => (
                    <tr key={r.recommendation_id}>
                      <td className="px-3 py-2.5 font-medium">{r.customer_id}</td>
                      <td className="px-3 py-2.5"><span className="capitalize">{labelise(r.category)}</span>{r.action_name && <span className="block text-xs text-slate-500">{r.action_name}</span>}</td>
                      <td className="max-w-md px-3 py-2.5 text-slate-700">{r.reason}</td>
                      <td className="px-3 py-2.5">{r.risk_band}</td>
                      <td className="px-3 py-2.5"><PriorityBadge priority={r.priority} /></td>
                      <td className="px-3 py-2.5"><WorkflowStatusBadge status={r.status} /></td>
                      <td className="px-3 py-2.5 text-xs text-slate-500">{r.created_at}</td>
                      <td className="px-3 py-2.5"><Evidence rec={r} /></td>
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
