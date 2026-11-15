import { useState, type FormEvent } from 'react';
import { Link, useNavigate, useParams } from 'react-router-dom';
import { AsyncBoundary } from '../../components/AsyncBoundary';
import { Card } from '../../components/Card';
import { DecisionBadge } from '../../components/DecisionBadge';
import { EmptyState } from '../../components/EmptyState';
import { ErrorState } from '../../components/ErrorState';
import { LoadingSkeleton } from '../../components/LoadingSkeleton';
import { MetricCard } from '../../components/MetricCard';
import { EstimateBadge, TierBadge } from '../../components/retention/badges';
import { useAsync } from '../../hooks/useAsync';
import { NotFoundError } from '../../services/api/errors';
import { useRetention } from '../../services/retention';
import type { ActionOption } from '../../types/retention';
import { formatPercent, formatSigned } from '../../utils/format';
import { formatMoney } from '../../utils/money';

function LookupForm({ initial }: { initial: string }) {
  const [value, setValue] = useState(initial);
  const navigate = useNavigate();
  const submit = (event: FormEvent) => {
    event.preventDefault();
    const id = value.trim();
    if (id) navigate(`/retention/recommendations/${encodeURIComponent(id)}`);
  };
  return (
    <form onSubmit={submit} className="flex flex-wrap items-end gap-3">
      <div>
        <label htmlFor="rec-customer" className="field-label">Customer ID</label>
        <input id="rec-customer" value={value} onChange={(e) => setValue(e.target.value)} placeholder="e.g. 7590-VHVEG" className="field w-auto" />
      </div>
      <button type="submit" className="btn btn-primary">Get recommendation</button>
    </form>
  );
}

function ActionRow({ a, primary }: { a: ActionOption; primary?: boolean }) {
  return (
    <tr className={primary ? 'bg-brand-50' : undefined}>
      <td className="px-3 py-2.5 font-medium">{a.name}{primary && <span className="ml-2 text-xs text-brand-700">recommended</span>}</td>
      <td className="px-3 py-2.5 text-right tabular-nums">{formatMoney(a.cost)}</td>
      <td className="px-3 py-2.5 text-right tabular-nums">{formatPercent(a.success_rate, 0)}</td>
      <td className="px-3 py-2.5 text-right tabular-nums">{formatMoney(a.expected_benefit)}</td>
      <td className="px-3 py-2.5 text-right tabular-nums">{formatMoney(a.expected_net_benefit)}</td>
    </tr>
  );
}

export function RetentionRecommendationPage() {
  const { customerId = '' } = useParams();
  const service = useRetention();
  const id = decodeURIComponent(customerId);
  const state = useAsync(() => (id ? service.getRecommendation(id) : Promise.resolve(null)), [service, id]);

  if (!id) {
    return (
      <Card title="Customer campaign recommendation" description="Look up any customer, or open one from the Priorities list.">
        <LookupForm initial="" />
      </Card>
    );
  }
  if (state.status === 'error' && state.error instanceof NotFoundError) {
    return (
      <div className="space-y-4">
        <LookupForm initial={id} />
        <EmptyState title="Customer not found" description={`No customer "${id}" exists in the scored portfolio.`} />
      </div>
    );
  }
  if (state.status === 'error') {
    return <ErrorState title="Unable to load the recommendation." message={state.error?.message} onRetry={state.reload} />;
  }

  return (
    <div className="space-y-6">
      <LookupForm initial={id} />
      <AsyncBoundary state={state} skeleton={<LoadingSkeleton variant="page" />} errorTitle="Unable to load the recommendation.">
        {(r) =>
          r && (
            <>
              <Card title={`Recommendation for ${r.customer_id}`} actions={<EstimateBadge />}>
                <div className="grid gap-3 sm:grid-cols-2 lg:grid-cols-4">
                  <MetricCard label="Phase 4 decision" value={<DecisionBadge decision={r.decision === 'INTERVENE' ? 'Intervene' : 'Do not intervene'} />} />
                  <MetricCard label="Recommended action" value={<span className="text-base">{r.primary_action?.name ?? 'No action'}</span>} />
                  <MetricCard label="Priority" value={<span className="flex items-center gap-2"><TierBadge tier={r.priority_tier} /> #{r.priority_rank}</span>} sub={`score ${r.priority_score.toFixed(1)} / 100 (heuristic)`} />
                  <MetricCard label="Est. net benefit" value={r.primary_action ? formatMoney(r.primary_action.expected_net_benefit) : '—'} sub="under assumed success rate" />
                </div>
                <h3 className="mb-2 mt-5 text-sm font-semibold text-slate-800">Why this recommendation</h3>
                <ul className="list-disc space-y-1 pl-5 text-sm text-slate-700">
                  {r.reasons.map((reason) => <li key={reason}>{reason}</li>)}
                  <li>{r.segment_peer_note}</li>
                </ul>
              </Card>

              <Card title="Actions compared" description="All eligible Phase 4 actions, estimates under assumed success rates">
                <div className="overflow-x-auto rounded-lg border border-slate-200">
                  <table className="w-full min-w-[560px] text-sm">
                    <caption className="sr-only">Actions compared</caption>
                    <thead className="bg-slate-50 text-xs text-slate-600">
                      <tr>
                        <th scope="col" className="px-3 py-2.5 text-left">Action</th>
                        <th scope="col" className="px-3 py-2.5 text-right">Cost</th>
                        <th scope="col" className="px-3 py-2.5 text-right">Assumed success</th>
                        <th scope="col" className="px-3 py-2.5 text-right">Est. benefit</th>
                        <th scope="col" className="px-3 py-2.5 text-right">Est. net benefit</th>
                      </tr>
                    </thead>
                    <tbody className="divide-y divide-slate-100">
                      {r.primary_action && <ActionRow a={r.primary_action} primary />}
                      {r.alternatives.map((a) => <ActionRow key={a.action_id} a={a} />)}
                    </tbody>
                  </table>
                </div>
              </Card>

              <Card title="Model drivers (SHAP)" description={r.explainability_note}>
                {r.explainability_available ? (
                  <ul className="space-y-1 text-sm">
                    {r.drivers.map((d) => (
                      <li key={d.feature} className="flex justify-between gap-3">
                        <span>{d.feature} = {String(d.raw_value ?? 'n/a')}</span>
                        <span className="tabular-nums text-rose-700">{formatSigned(d.shap_value)}</span>
                      </li>
                    ))}
                  </ul>
                ) : (
                  <p className="text-sm text-slate-600">Explainability is not available right now; the recommendation above does not depend on it.</p>
                )}
              </Card>

              <p className="text-xs text-slate-500">
                Basis: {r.basis}. Causal claim: {r.causal_claim ? 'yes' : 'no'}. Uplift model available: {r.uplift_available ? 'yes' : 'no'}. {r.note}{' '}
                <Link to="/retention/simulator" className="text-brand-700 hover:underline">Open the simulator</Link>
              </p>
            </>
          )
        }
      </AsyncBoundary>
    </div>
  );
}
