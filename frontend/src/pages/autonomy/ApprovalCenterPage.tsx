import { useMemo, useState } from 'react';
import { AsyncBoundary } from '../../components/AsyncBoundary';
import { Card } from '../../components/Card';
import { LoadingSkeleton } from '../../components/LoadingSkeleton';
import { Pagination } from '../../components/Pagination';
import { ConfirmPanel, Notice, WorkflowStatusBadge, labelise } from '../../components/autonomy/parts';
import { useAsync } from '../../hooks/useAsync';
import { toError } from '../../services/api/errors';
import { newIdempotencyKey, useAutonomy } from '../../services/autonomy';
import type { AutonomyRecommendation, RecommendationQuery, WorkflowAction, WorkflowStatus } from '../../types/autonomy';

const STATUSES: WorkflowStatus[] = ['pending', 'approved', 'rejected', 'executed', 'failed', 'cancelled'];
const ACTIONS_FOR: Record<WorkflowStatus, WorkflowAction[]> = {
  pending: ['approve', 'reject', 'cancel'],
  approved: ['execute', 'fail', 'cancel'],
  rejected: [], executed: [], failed: [], cancelled: [],
};
const COPY: Record<WorkflowAction, { label: string; confirm: string }> = {
  approve: { label: 'Approve', confirm: 'Approving records your decision. It does NOT send anything to the customer.' },
  reject: { label: 'Reject', confirm: 'Rejecting closes this recommendation. This cannot be undone.' },
  cancel: { label: 'Cancel', confirm: 'Cancelling closes this recommendation. This cannot be undone.' },
  execute: { label: 'Mark executed', confirm: 'Only record this if your team has already carried out the action manually. TriChurn sends nothing.' },
  fail: { label: 'Mark failed', confirm: 'Record that the approved action could not be carried out.' },
};

export function ApprovalCenterPage() {
  const service = useAutonomy();
  const summary = useAsync(() => service.getSummary(), [service]);
  const [status, setStatus] = useState<WorkflowStatus>('pending');
  const [page, setPage] = useState(1);
  const [version, setVersion] = useState(0);
  const [target, setTarget] = useState<{ rec: AutonomyRecommendation; action: WorkflowAction } | null>(null);
  const [busy, setBusy] = useState(false);
  const [message, setMessage] = useState<{ tone: 'ok' | 'error'; text: string } | null>(null);

  const query = useMemo<RecommendationQuery>(() => ({ page, pageSize: 25, status }), [page, status]);
  const state = useAsync(() => service.getRecommendations(query), [service, query, version]);
  const available = summary.data?.status.approvals_available ?? false;

  const submit = async (note: string) => {
    if (!target) return;
    setBusy(true);
    try {
      const updated = await service.transition(target.rec.recommendation_id, target.action, note.trim() || undefined, newIdempotencyKey());
      setMessage({ tone: 'ok', text: `${target.rec.customer_id}: now ${updated.status}.` });
      setTarget(null);
      setVersion((v) => v + 1);
    } catch (e) {
      setMessage({ tone: 'error', text: toError(e).message });
      setTarget(null);
    } finally {
      setBusy(false);
    }
  };

  return (
    <div className="space-y-6">
      {summary.status === 'success' && !available && (
        <Notice tone="warn">
          Approval actions are disabled. No identity provider is configured, so no one can be an authorised reviewer. You can inspect recommendations here; approve / reject / execute will stay unavailable until access control is implemented.
        </Notice>
      )}
      {message && <Notice tone={message.tone}>{message.text}</Notice>}
      <Card>
        <label htmlFor="ap-status" className="field-label">Status</label>
        <select id="ap-status" className="field w-auto" value={status} onChange={(e) => { setStatus(e.target.value as WorkflowStatus); setPage(1); }}>
          {STATUSES.map((s) => <option key={s} value={s}>{s}</option>)}
        </select>
      </Card>
      <AsyncBoundary
        state={state}
        skeleton={<LoadingSkeleton variant="table" />}
        isEmpty={(p) => p.total === 0}
        emptyTitle={`No ${status} recommendations`}
        emptyDescription="Generate recommendations in the Command Center to populate the queue."
        errorTitle="Unable to load the approval queue."
      >
        {(p) => (
          <Card>
            <div className="overflow-x-auto rounded-lg border border-slate-200">
              <table className="w-full min-w-[860px] text-sm">
                <caption className="sr-only">Approval queue</caption>
                <thead className="bg-slate-50 text-xs text-slate-600">
                  <tr>{['Customer', 'Recommendation', 'Priority', 'Status', 'Actions'].map((h) => <th key={h} scope="col" className="px-3 py-2.5 text-left">{h}</th>)}</tr>
                </thead>
                <tbody className="divide-y divide-slate-100">
                  {p.items.map((r) => (
                    <tr key={r.recommendation_id}>
                      <td className="px-3 py-2.5 font-medium">{r.customer_id}</td>
                      <td className="px-3 py-2.5"><span className="capitalize">{labelise(r.category)}</span><span className="block max-w-md text-xs text-slate-500">{r.reason}</span></td>
                      <td className="px-3 py-2.5">{r.priority}</td>
                      <td className="px-3 py-2.5"><WorkflowStatusBadge status={r.status} /></td>
                      <td className="px-3 py-2.5">
                        <div className="flex flex-wrap gap-2">
                          {ACTIONS_FOR[r.status].map((a) => (
                            <button key={a} type="button" disabled={!available} onClick={() => setTarget({ rec: r, action: a })}
                              aria-label={`${COPY[a].label} ${r.customer_id}`}
                              className="btn btn-secondary btn-sm">
                              {COPY[a].label}
                            </button>
                          ))}
                          {ACTIONS_FOR[r.status].length === 0 && <span className="text-xs text-slate-500">Closed</span>}
                        </div>
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
            <Pagination page={p.page} pageCount={p.page_count} total={p.total} pageSize={p.page_size} onPageChange={setPage} />
          </Card>
        )}
      </AsyncBoundary>
      <ConfirmPanel
        open={target !== null}
        title={target ? `${COPY[target.action].label}: ${target.rec.customer_id}` : 'Confirm'}
        description={target ? COPY[target.action].confirm : ''}
        confirmLabel={target ? `Confirm: ${COPY[target.action].label}` : 'Confirm'}
        busy={busy}
        onConfirm={(note) => void submit(note)}
        onCancel={() => setTarget(null)}
      />
    </div>
  );
}
