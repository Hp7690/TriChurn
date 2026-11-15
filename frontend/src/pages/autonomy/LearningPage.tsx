import { useState, type FormEvent } from 'react';
import { AsyncBoundary } from '../../components/AsyncBoundary';
import { Card } from '../../components/Card';
import { EmptyState } from '../../components/EmptyState';
import { LoadingSkeleton } from '../../components/LoadingSkeleton';
import { Pagination } from '../../components/Pagination';
import { Notice } from '../../components/autonomy/parts';
import { useAsync } from '../../hooks/useAsync';
import { toError } from '../../services/api/errors';
import { newIdempotencyKey, useAutonomy } from '../../services/autonomy';
import type { FeedbackOutcome } from '../../types/autonomy';
import { formatPercent } from '../../utils/format';

const field = 'field';

export function LearningPage() {
  const service = useAutonomy();
  const [version, setVersion] = useState(0);
  const [page, setPage] = useState(1);
  const report = useAsync(() => service.getLearning(), [service, version]);
  const feedback = useAsync(() => service.getFeedback(page, 25), [service, page, version]);
  const summary = useAsync(() => service.getSummary(), [service]);
  const available = summary.data?.status.approvals_available ?? false;

  const [recId, setRecId] = useState('');
  const [outcome, setOutcome] = useState<FeedbackOutcome>('retained');
  const [outcomeAt, setOutcomeAt] = useState('');
  const [source, setSource] = useState('');
  const [campaign, setCampaign] = useState('');
  const [message, setMessage] = useState<{ tone: 'ok' | 'error'; text: string } | null>(null);

  const record = async (event: FormEvent) => {
    event.preventDefault();
    try {
      await service.recordFeedback({ recommendationId: recId.trim(), outcome, outcomeAt, dataSource: source.trim(), campaignId: campaign.trim() || undefined }, newIdempotencyKey());
      setMessage({ tone: 'ok', text: 'Observed outcome recorded.' });
      setVersion((v) => v + 1);
    } catch (e) {
      setMessage({ tone: 'error', text: toError(e).message });
    }
  };

  return (
    <div className="space-y-6">
      <AsyncBoundary state={report} skeleton={<LoadingSkeleton variant="card" />} errorTitle="Unable to load the learning report.">
        {(r) => (
          <>
            <Notice tone="warn">{r.note}</Notice>
            <Card title="Feedback evaluation" description={r.observed_vs_estimated}>
              <p className="mb-3 text-sm">Validated observed outcomes: <strong>{r.validated_outcomes}</strong> · Learning: <strong>{r.learning_enabled ? 'enabled' : 'not enabled'}</strong></p>
              {r.by_action.length === 0 ? (
                <p className="text-sm text-slate-600">No outcomes recorded yet.</p>
              ) : (
                <div className="overflow-x-auto rounded-lg border border-slate-200">
                  <table className="w-full min-w-[520px] text-sm">
                    <caption className="sr-only">Observed outcomes by action</caption>
                    <thead className="bg-slate-50 text-xs text-slate-600"><tr><th scope="col" className="px-3 py-2.5 text-left">Action</th><th scope="col" className="px-3 py-2.5 text-right">Outcomes</th><th scope="col" className="px-3 py-2.5 text-right">Observed retained share</th></tr></thead>
                    <tbody className="divide-y divide-slate-100">
                      {r.by_action.map((a) => <tr key={a.action}><td className="px-3 py-2.5">{a.action}</td><td className="px-3 py-2.5 text-right tabular-nums">{a.total}</td><td className="px-3 py-2.5 text-right tabular-nums">{formatPercent(a.observed_retained_share, 0)}</td></tr>)}
                    </tbody>
                  </table>
                </div>
              )}
              <h3 className="mb-2 mt-4 text-sm font-semibold">Readiness checks</h3>
              <ul className="space-y-1 text-sm">
                {r.checks.map((c) => <li key={c.code} className="flex gap-2"><span aria-hidden="true">{c.passed ? '✓' : '✗'}</span><span className="sr-only">{c.passed ? 'Passed:' : 'Not met:'}</span><span>{c.detail}</span></li>)}
              </ul>
            </Card>
          </>
        )}
      </AsyncBoundary>

      <AsyncBoundary state={feedback} skeleton={<LoadingSkeleton variant="table" />} isEmpty={(p) => p.total === 0} emptyTitle="No feedback recorded" emptyDescription="Observed outcomes can only be recorded for executed recommendations." errorTitle="Unable to load feedback.">
        {(p) => (
          <Card title="Recorded outcomes (observed)">
            <div className="overflow-x-auto rounded-lg border border-slate-200">
              <table className="w-full min-w-[760px] text-sm">
                <caption className="sr-only">Feedback</caption>
                <thead className="bg-slate-50 text-xs text-slate-600"><tr>{['Customer', 'Action', 'Decision', 'Outcome', 'Outcome date', 'Source'].map((h) => <th key={h} scope="col" className="px-3 py-2.5 text-left">{h}</th>)}</tr></thead>
                <tbody className="divide-y divide-slate-100">
                  {p.items.map((f) => <tr key={f.feedback_id}><td className="px-3 py-2.5">{f.customer_id}</td><td className="px-3 py-2.5">{f.recommended_action ?? '—'}</td><td className="px-3 py-2.5">{f.approval_decision}</td><td className="px-3 py-2.5">{f.outcome}</td><td className="px-3 py-2.5">{f.outcome_at}</td><td className="px-3 py-2.5">{f.data_source}</td></tr>)}
                </tbody>
              </table>
            </div>
            <Pagination page={p.page} pageCount={p.page_count} total={p.total} pageSize={p.page_size} onPageChange={setPage} />
          </Card>
        )}
      </AsyncBoundary>

      <Card title="Record an observed outcome" description="Only for recommendations marked executed. Never enter estimates here.">
        {!available && <div className="mb-3"><Notice tone="warn">Recording is disabled until an identity provider is configured.</Notice></div>}
        {message && <div className="mb-3"><Notice tone={message.tone}>{message.text}</Notice></div>}
        <form onSubmit={(e) => void record(e)} className="grid gap-3 sm:grid-cols-2 lg:grid-cols-5" aria-label="Record outcome">
          <div><label htmlFor="fb-rec" className="field-label">Recommendation ID</label><input id="fb-rec" required className={field} value={recId} onChange={(e) => setRecId(e.target.value)} /></div>
          <div><label htmlFor="fb-outcome" className="field-label">Outcome</label>
            <select id="fb-outcome" className={field} value={outcome} onChange={(e) => setOutcome(e.target.value as FeedbackOutcome)}><option value="retained">Retained</option><option value="churned">Churned</option><option value="no_response">No response</option></select></div>
          <div><label htmlFor="fb-date" className="field-label">Outcome date</label><input id="fb-date" type="date" required className={field} value={outcomeAt} onChange={(e) => setOutcomeAt(e.target.value)} /></div>
          <div><label htmlFor="fb-source" className="field-label">Data source</label><input id="fb-source" required className={field} value={source} onChange={(e) => setSource(e.target.value)} /></div>
          <div><label htmlFor="fb-campaign" className="field-label">Campaign ID (optional)</label><input id="fb-campaign" className={field} value={campaign} onChange={(e) => setCampaign(e.target.value)} /></div>
          <div className="sm:col-span-2 lg:col-span-5"><button type="submit" disabled={!available} className="btn btn-primary">Record outcome</button></div>
        </form>
      </Card>
      {feedback.status === 'success' && feedback.data?.total === 0 && report.status === 'error' && <EmptyState title="Nothing to show" />}
    </div>
  );
}
