import { useState, type FormEvent } from 'react';
import { AsyncBoundary } from '../../components/AsyncBoundary';
import { Card } from '../../components/Card';
import { EmptyState } from '../../components/EmptyState';
import { LoadingSkeleton } from '../../components/LoadingSkeleton';
import { ObservedBadge, EstimateBadge } from '../../components/retention/badges';
import { useAsync } from '../../hooks/useAsync';
import { toError } from '../../services/api/errors';
import { useRetention } from '../../services/retention';
import type { CampaignGroup, CampaignOutcome } from '../../types/retention';
import { formatPercent } from '../../utils/format';
import { formatMoney, formatRatio } from '../../utils/money';

const field = 'field';
const dash = (v: number | null) => (v === null ? '—' : formatMoney(v));

function splitIds(text: string): string[] {
  return Array.from(new Set(text.split(/[\s,;]+/).map((s) => s.trim()).filter(Boolean)));
}

export function RetentionCampaignsPage() {
  const service = useRetention();
  const [version, setVersion] = useState(0);
  const analytics = useAsync(() => service.getAnalytics(), [service, version]);
  const readiness = useAsync(() => service.getUpliftReadiness(), [service, version]);
  const actions = useAsync(() => service.getActions(), [service]);
  const refresh = () => setVersion((v) => v + 1);

  const [message, setMessage] = useState<{ kind: 'ok' | 'error'; text: string } | null>(null);
  const [name, setName] = useState('');
  const [actionId, setActionId] = useState('');
  const [date, setDate] = useState('');
  const [randomized, setRandomized] = useState(false);
  const [assignCampaign, setAssignCampaign] = useState('');
  const [assignIds, setAssignIds] = useState('');
  const [group, setGroup] = useState<CampaignGroup>('unspecified');
  const [outCampaign, setOutCampaign] = useState('');
  const [outCustomer, setOutCustomer] = useState('');
  const [outcome, setOutcome] = useState<CampaignOutcome>('retained');
  const [outCost, setOutCost] = useState('');
  const [outRevenue, setOutRevenue] = useState('');

  const attempt = async (work: () => Promise<string>) => {
    try {
      setMessage({ kind: 'ok', text: await work() });
      refresh();
    } catch (e) {
      setMessage({ kind: 'error', text: toError(e).message });
    }
  };

  const create = (event: FormEvent) => {
    event.preventDefault();
    void attempt(async () => {
      const c = await service.createCampaign({ name, actionId: actionId || (actions.data?.actions[0]?.action_id ?? ''), campaignDate: date, randomized });
      setName('');
      return `Campaign ${c.campaign_id} created.`;
    });
  };
  const assign = (event: FormEvent) => {
    event.preventDefault();
    void attempt(async () => {
      const r = await service.assignCustomers(assignCampaign, splitIds(assignIds), group);
      return `Assigned ${r.assigned} of ${r.requested}. Unknown: ${r.unknown_customer_ids.length}, ineligible: ${r.ineligible_customer_ids.length}, already assigned: ${r.already_assigned_ids.length}.`;
    });
  };
  const record = (event: FormEvent) => {
    event.preventDefault();
    void attempt(async () => {
      const r = await service.recordOutcomes(outCampaign, [{
        customerId: outCustomer.trim(), outcome,
        actualCost: outCost.trim() === '' ? undefined : Number(outCost),
        actualRetainedRevenue: outRevenue.trim() === '' ? undefined : Number(outRevenue),
      }]);
      return r.recorded === 1 ? 'Outcome recorded.' : `Not recorded (not assigned: ${r.not_assigned_ids.length}, already recorded: ${r.already_recorded_ids.length}).`;
    });
  };

  return (
    <div className="space-y-6">
      <AsyncBoundary state={analytics} skeleton={<LoadingSkeleton variant="table" />} errorTitle="Unable to load campaign analytics.">
        {(a) =>
          a.campaigns.length === 0 ? (
            <EmptyState title="No campaigns recorded yet" description="Nothing is shown until real campaigns, assignments and outcomes are recorded. No historical results are generated or assumed." />
          ) : (
            <Card title="Campaign performance" description={a.note}>
              <div className="overflow-x-auto rounded-lg border border-slate-200">
                <table className="w-full min-w-[1100px] text-sm">
                  <caption className="sr-only">Campaign performance</caption>
                  <thead className="bg-slate-50 text-xs text-slate-600">
                    <tr>
                      <th scope="col" className="px-3 py-2.5 text-left">Campaign</th>
                      <th scope="col" className="px-3 py-2.5 text-right">Assigned</th>
                      <th scope="col" className="px-3 py-2.5 text-right">Outcomes</th>
                      <th scope="col" className="px-3 py-2.5 text-right">Observed retention</th>
                      <th scope="col" className="px-3 py-2.5 text-right">Est. cost <EstimateBadge /></th>
                      <th scope="col" className="px-3 py-2.5 text-right">Est. benefit <EstimateBadge /></th>
                      <th scope="col" className="px-3 py-2.5 text-right">Actual cost <ObservedBadge /></th>
                      <th scope="col" className="px-3 py-2.5 text-right">Actual retained revenue <ObservedBadge /></th>
                      <th scope="col" className="px-3 py-2.5 text-right">Actual ROI</th>
                    </tr>
                  </thead>
                  <tbody className="divide-y divide-slate-100">
                    {a.campaigns.map((c) => (
                      <tr key={c.campaign_id}>
                        <td className="px-3 py-2.5"><span className="font-medium">{c.name}</span><span className="block text-xs text-slate-500">{c.campaign_id} · {c.action_id} · {c.campaign_date}{c.randomized ? ' · randomised' : ''}</span></td>
                        <td className="px-3 py-2.5 text-right tabular-nums">{c.assigned}</td>
                        <td className="px-3 py-2.5 text-right tabular-nums">{c.outcomes_recorded} ({c.outcome_coverage === null ? '—' : formatPercent(c.outcome_coverage, 0)})</td>
                        <td className="px-3 py-2.5 text-right tabular-nums">{c.observed_retention_rate === null ? '—' : formatPercent(c.observed_retention_rate, 0)}</td>
                        <td className="px-3 py-2.5 text-right tabular-nums">{formatMoney(c.estimated_cost)}</td>
                        <td className="px-3 py-2.5 text-right tabular-nums">{formatMoney(c.estimated_benefit)}</td>
                        <td className="px-3 py-2.5 text-right tabular-nums">{dash(c.actual_cost)}</td>
                        <td className="px-3 py-2.5 text-right tabular-nums">{dash(c.actual_retained_revenue)}</td>
                        <td className="px-3 py-2.5 text-right tabular-nums">{formatRatio(c.actual_roi)}</td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            </Card>
          )
        }
      </AsyncBoundary>

      <AsyncBoundary state={readiness} skeleton={<LoadingSkeleton variant="card" />} errorTitle="Unable to load uplift readiness.">
        {(r) => (
          <Card title="Uplift modelling readiness" description={r.note}>
            <p className="mb-3 text-sm">
              Status: <strong className={r.ready ? 'text-emerald-700' : 'text-rose-700'}>{r.status.replace(/_/g, ' ')}</strong>
              {' · '}treatment {r.treatment_assignments} · control {r.control_assignments} · outcomes {r.outcomes_recorded}
            </p>
            <ul className="space-y-1 text-sm">
              {r.checks.map((c) => (
                <li key={c.code} className="flex gap-2">
                  <span aria-hidden="true">{c.passed ? '✓' : '✗'}</span>
                  <span className="sr-only">{c.passed ? 'Passed:' : 'Not met:'}</span>
                  <span>{c.detail}</span>
                </li>
              ))}
            </ul>
            <details className="mt-3">
              <summary className="cursor-pointer text-sm text-brand-700">What uplift modelling would require</summary>
              <ul className="mt-2 list-disc space-y-1 pl-5 text-sm text-slate-700">{r.requirements.map((q) => <li key={q}>{q}</li>)}</ul>
            </details>
          </Card>
        )}
      </AsyncBoundary>

      <Card title="Record campaign activity" description="Only real activity belongs here. Estimated figures are snapshotted from Phase 4 when a customer is assigned; actuals are exactly what you enter.">
        {message && (
          <p role={message.kind === 'error' ? 'alert' : 'status'} className={message.kind === 'error' ? 'mb-3 rounded bg-rose-50 px-3 py-2 text-sm text-rose-800' : 'mb-3 rounded bg-emerald-50 px-3 py-2 text-sm text-emerald-800'}>
            {message.text}
          </p>
        )}
        <div className="grid gap-6 lg:grid-cols-3">
          <form onSubmit={create} className="space-y-3" aria-label="Create campaign">
            <h3 className="text-sm font-semibold">1. Create campaign</h3>
            <div><label htmlFor="cc-name" className="field-label">Name</label><input id="cc-name" required className={field} value={name} onChange={(e) => setName(e.target.value)} /></div>
            <div>
              <label htmlFor="cc-action" className="field-label">Campaign type (Phase 4 action)</label>
              <select id="cc-action" className={field} value={actionId} onChange={(e) => setActionId(e.target.value)}>
                {(actions.data?.actions ?? []).map((a) => <option key={a.action_id} value={a.action_id}>{a.name}</option>)}
              </select>
            </div>
            <div><label htmlFor="cc-date" className="field-label">Campaign date</label><input id="cc-date" type="date" required className={field} value={date} onChange={(e) => setDate(e.target.value)} /></div>
            <label className="inline-flex items-center gap-2 text-sm"><input type="checkbox" checked={randomized} onChange={(e) => setRandomized(e.target.checked)} /> Customers were randomly assigned</label>
            <button type="submit" className="btn btn-primary">Create campaign</button>
          </form>

          <form onSubmit={assign} className="space-y-3" aria-label="Assign customers">
            <h3 className="text-sm font-semibold">2. Assign customers</h3>
            <div><label htmlFor="as-campaign" className="field-label">Campaign ID</label><input id="as-campaign" required className={field} value={assignCampaign} onChange={(e) => setAssignCampaign(e.target.value)} /></div>
            <div><label htmlFor="as-ids" className="field-label">Customer IDs (comma or space separated)</label><textarea id="as-ids" required rows={3} className={field} value={assignIds} onChange={(e) => setAssignIds(e.target.value)} /></div>
            <div>
              <label htmlFor="as-group" className="field-label">Group</label>
              <select id="as-group" className={field} value={group} onChange={(e) => setGroup(e.target.value as CampaignGroup)}>
                <option value="unspecified">Unspecified</option><option value="treatment">Treatment</option><option value="control">Control (receives nothing)</option>
              </select>
            </div>
            <button type="submit" className="btn btn-primary">Assign customers</button>
          </form>

          <form onSubmit={record} className="space-y-3" aria-label="Record outcome">
            <h3 className="text-sm font-semibold">3. Record an outcome</h3>
            <div><label htmlFor="oc-campaign" className="field-label">Campaign ID</label><input id="oc-campaign" required className={field} value={outCampaign} onChange={(e) => setOutCampaign(e.target.value)} /></div>
            <div><label htmlFor="oc-customer" className="field-label">Customer ID</label><input id="oc-customer" required className={field} value={outCustomer} onChange={(e) => setOutCustomer(e.target.value)} /></div>
            <div>
              <label htmlFor="oc-outcome" className="field-label">Outcome</label>
              <select id="oc-outcome" className={field} value={outcome} onChange={(e) => setOutcome(e.target.value as CampaignOutcome)}>
                <option value="retained">Retained</option><option value="churned">Churned</option><option value="no_response">No response</option>
              </select>
            </div>
            <div className="grid grid-cols-2 gap-2">
              <div><label htmlFor="oc-cost" className="field-label">Actual cost</label><input id="oc-cost" inputMode="decimal" className={field} value={outCost} onChange={(e) => setOutCost(e.target.value)} /></div>
              <div><label htmlFor="oc-rev" className="field-label">Retained revenue</label><input id="oc-rev" inputMode="decimal" className={field} value={outRevenue} onChange={(e) => setOutRevenue(e.target.value)} /></div>
            </div>
            <button type="submit" className="btn btn-primary">Record outcome</button>
          </form>
        </div>
      </Card>
    </div>
  );
}
