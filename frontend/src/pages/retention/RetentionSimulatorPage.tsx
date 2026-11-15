import { useState, type FormEvent } from 'react';
import { ScenarioComparisonChart } from '../../charts/RetentionCharts';
import { AsyncBoundary } from '../../components/AsyncBoundary';
import { Card } from '../../components/Card';
import { ErrorState } from '../../components/ErrorState';
import { LoadingSkeleton } from '../../components/LoadingSkeleton';
import { EstimateBadge } from '../../components/retention/badges';
import { useAsync } from '../../hooks/useAsync';
import { toError } from '../../services/api/errors';
import { useRetention } from '../../services/retention';
import type { ScenarioInput, SimulationResult } from '../../types/retention';
import { formatNumber, formatPercent } from '../../utils/format';
import { formatMoney, formatRatio } from '../../utils/money';

const MAX_SCENARIOS = 4;
const RISK_BANDS = ['LOW', 'MEDIUM', 'HIGH', 'CRITICAL'];
const field = 'field';

interface Draft {
  key: number;
  actionId: string;
  cost: string;
  success: string; // percent, e.g. "25"
  decisionFilter: 'intervene' | 'any';
  riskBands: string[];
  topN: string;
}

const blank = (key: number, actionId: string): Draft => ({ key, actionId, cost: '', success: '', decisionFilter: 'intervene', riskBands: [], topN: '' });

function toInput(d: Draft, index: number): ScenarioInput {
  return {
    name: `Scenario ${index + 1}`,
    actionId: d.actionId,
    costOverride: d.cost.trim() === '' ? undefined : Number(d.cost),
    successRateOverride: d.success.trim() === '' ? undefined : Number(d.success) / 100,
    decisionFilter: d.decisionFilter,
    riskBands: d.riskBands,
    topN: d.topN.trim() === '' ? undefined : Number(d.topN),
  };
}

function validate(d: Draft): string | null {
  if (d.cost.trim() !== '' && !(Number(d.cost) >= 0)) return 'Cost override must be a number ≥ 0.';
  if (d.success.trim() !== '' && !(Number(d.success) >= 0 && Number(d.success) <= 100)) return 'Success rate must be between 0 and 100.';
  if (d.topN.trim() !== '' && !(Number.isInteger(Number(d.topN)) && Number(d.topN) >= 1)) return 'Top N must be a whole number ≥ 1.';
  return null;
}

export function RetentionSimulatorPage() {
  const service = useRetention();
  const actions = useAsync(() => service.getActions(), [service]);
  const [drafts, setDrafts] = useState<Draft[]>([]);
  const [nextKey, setNextKey] = useState(2);
  const [result, setResult] = useState<SimulationResult | null>(null);
  const [running, setRunning] = useState(false);
  const [error, setError] = useState<Error | null>(null);

  const catalogue = actions.data;
  const list = drafts.length > 0 ? drafts : catalogue ? [blank(1, catalogue.actions[0]?.action_id ?? '')] : [];
  const problems = list.map(validate);

  const patch = (key: number, change: Partial<Draft>) => {
    const base = drafts.length > 0 ? drafts : list;
    setDrafts(base.map((d) => (d.key === key ? { ...d, ...change } : d)));
  };

  const run = async (event: FormEvent) => {
    event.preventDefault();
    if (problems.some(Boolean)) return;
    setRunning(true);
    setError(null);
    try {
      setResult(await service.simulate(list.map(toInput)));
    } catch (e) {
      setError(toError(e));
    } finally {
      setRunning(false);
    }
  };

  const currency = catalogue?.currency_code ?? 'INR';

  return (
    <div className="space-y-6">
      <AsyncBoundary state={actions} skeleton={<LoadingSkeleton variant="card" />} isEmpty={(a) => a.actions.length === 0} emptyTitle="No retention actions configured" errorTitle="Unable to load retention actions.">
        {(a) => (
          <form onSubmit={run} className="space-y-4" aria-label="Campaign scenarios">
            <Card title="Scenario builder" description={`Costs and success rates default to the Phase 4 catalogue (${a.currency_code}). Overrides explore ASSUMPTIONS; results are estimates.`} actions={<EstimateBadge />}>
              <div className="space-y-4">
                {list.map((d, i) => (
                  <fieldset key={d.key} className="rounded-lg border border-slate-200 p-4">
                    <legend className="px-1 text-sm font-semibold text-slate-800">Scenario {i + 1}</legend>
                    <div className="grid gap-3 sm:grid-cols-2 lg:grid-cols-4">
                      <div>
                        <label htmlFor={`sc-action-${d.key}`} className="field-label">Action</label>
                        <select id={`sc-action-${d.key}`} className={field} value={d.actionId} onChange={(e) => patch(d.key, { actionId: e.target.value })}>
                          {a.actions.map((x) => <option key={x.action_id} value={x.action_id}>{x.name} ({formatMoney(x.cost, a.currency_code)}, {formatPercent(x.success_rate, 0)})</option>)}
                        </select>
                      </div>
                      <div>
                        <label htmlFor={`sc-cost-${d.key}`} className="field-label">Cost per customer (override)</label>
                        <input id={`sc-cost-${d.key}`} inputMode="decimal" className={field} value={d.cost} placeholder="catalogue value" onChange={(e) => patch(d.key, { cost: e.target.value })} />
                      </div>
                      <div>
                        <label htmlFor={`sc-success-${d.key}`} className="field-label">Success rate % (override)</label>
                        <input id={`sc-success-${d.key}`} inputMode="decimal" className={field} value={d.success} placeholder="catalogue value" onChange={(e) => patch(d.key, { success: e.target.value })} />
                      </div>
                      <div>
                        <label htmlFor={`sc-top-${d.key}`} className="field-label">Target top N by priority</label>
                        <input id={`sc-top-${d.key}`} inputMode="numeric" className={field} value={d.topN} placeholder="all matching" onChange={(e) => patch(d.key, { topN: e.target.value })} />
                      </div>
                      <div>
                        <label htmlFor={`sc-dec-${d.key}`} className="field-label">Customers</label>
                        <select id={`sc-dec-${d.key}`} className={field} value={d.decisionFilter} onChange={(e) => patch(d.key, { decisionFilter: e.target.value as 'intervene' | 'any' })}>
                          <option value="intervene">Phase 4 intervention candidates</option>
                          <option value="any">Any customer</option>
                        </select>
                      </div>
                      <div className="sm:col-span-2 lg:col-span-3">
                        <span className="field-label">Risk bands (none selected = all)</span>
                        <div className="flex flex-wrap gap-3">
                          {RISK_BANDS.map((b) => (
                            <label key={b} className="inline-flex items-center gap-1.5 text-sm">
                              <input type="checkbox" checked={d.riskBands.includes(b)} onChange={(e) => patch(d.key, { riskBands: e.target.checked ? [...d.riskBands, b] : d.riskBands.filter((x) => x !== b) })} />
                              {b}
                            </label>
                          ))}
                        </div>
                      </div>
                    </div>
                    {problems[i] && <p role="alert" className="mt-2 text-xs text-rose-700">{problems[i]}</p>}
                    {list.length > 1 && (
                      <button type="button" onClick={() => setDrafts(list.filter((x) => x.key !== d.key))} className="mt-3 text-xs font-medium text-rose-700 hover:underline">Remove scenario</button>
                    )}
                  </fieldset>
                ))}
              </div>
              <div className="mt-4 flex flex-wrap items-center gap-3">
                <button type="button" disabled={list.length >= MAX_SCENARIOS} onClick={() => { setDrafts([...list, blank(nextKey, a.actions[0].action_id)]); setNextKey(nextKey + 1); }} className="btn btn-secondary">
                  Add scenario
                </button>
                <button type="submit" disabled={running || problems.some(Boolean)} className="btn btn-primary">
                  {running ? 'Running…' : 'Run simulation'}
                </button>
              </div>
            </Card>
          </form>
        )}
      </AsyncBoundary>

      {error && <ErrorState title="Unable to run the simulation." message={error.message} />}

      {result && (
        <>
          <Card title="Scenario comparison" description={result.note} actions={<EstimateBadge />}>
            <ScenarioComparisonChart data={result.results} currency={currency} />
          </Card>
          <Card title="Results (estimates)">
            <div className="overflow-x-auto rounded-lg border border-slate-200">
              <table className="w-full min-w-[980px] text-sm">
                <caption className="sr-only">Scenario results</caption>
                <thead className="bg-slate-50 text-xs text-slate-600">
                  <tr>
                    <th scope="col" className="px-3 py-2.5 text-left">Scenario</th>
                    <th scope="col" className="px-3 py-2.5 text-left">Assumptions</th>
                    <th scope="col" className="px-3 py-2.5 text-right">Customers</th>
                    <th scope="col" className="px-3 py-2.5 text-right">Est. cost</th>
                    <th scope="col" className="px-3 py-2.5 text-right">Est. retained revenue</th>
                    <th scope="col" className="px-3 py-2.5 text-right">Est. net benefit</th>
                    <th scope="col" className="px-3 py-2.5 text-right">Est. ROI</th>
                    <th scope="col" className="px-3 py-2.5 text-right">Exp. retained customers</th>
                  </tr>
                </thead>
                <tbody className="divide-y divide-slate-100">
                  {result.results.map((r, i) => (
                    <tr key={`${r.name}-${i}`}>
                      <td className="px-3 py-2.5 font-medium">
                        {r.name}: {r.action_name}
                        {result.best_by_net_benefit_index === i && <span className="ml-2 rounded bg-emerald-100 px-1.5 py-0.5 text-[11px] font-semibold text-emerald-900">best net benefit</span>}
                        {result.best_by_roi_index === i && <span className="ml-2 rounded bg-indigo-100 px-1.5 py-0.5 text-[11px] font-semibold text-indigo-900">best ROI</span>}
                      </td>
                      <td className="px-3 py-2.5 text-xs text-slate-600">
                        cost {formatMoney(r.cost_per_customer, currency)} ({r.cost_source === 'scenario_override' ? 'override' : 'Phase 4'}) · success {formatPercent(r.success_rate, 0)} ({r.success_rate_source === 'scenario_override' ? 'override' : 'Phase 4'})
                      </td>
                      <td className="px-3 py-2.5 text-right tabular-nums">
                        {formatNumber(r.eligible_customers)}
                        {r.excluded_ineligible > 0 && <span className="block text-xs text-slate-500">{formatNumber(r.excluded_ineligible)} ineligible</span>}
                      </td>
                      <td className="px-3 py-2.5 text-right tabular-nums">{formatMoney(r.total_cost, currency)}</td>
                      <td className="px-3 py-2.5 text-right tabular-nums">{formatMoney(r.estimated_retained_revenue, currency)}</td>
                      <td className="px-3 py-2.5 text-right tabular-nums">{formatMoney(r.estimated_net_benefit, currency)}</td>
                      <td className="px-3 py-2.5 text-right tabular-nums">{formatRatio(r.estimated_roi)}</td>
                      <td className="px-3 py-2.5 text-right tabular-nums">{r.expected_retained_customers.toLocaleString('en-US', { maximumFractionDigits: 1 })}</td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          </Card>
        </>
      )}
    </div>
  );
}
