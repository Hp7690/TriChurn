import { ArrowDown, ArrowRight, FlaskConical } from 'lucide-react';
import { useEffect, useState } from 'react';
import { useSearchParams } from 'react-router-dom';
import { AsyncBoundary } from '../components/AsyncBoundary';
import { Card } from '../components/Card';
import { DecisionBadge } from '../components/DecisionBadge';
import { ErrorState } from '../components/ErrorState';
import { LoadingSkeleton } from '../components/LoadingSkeleton';
import { PageHeader } from '../components/PageHeader';
import { useAsync } from '../hooks/useAsync';
import { useService } from '../services/ServiceContext';
import type { RetentionAction, WhatIfInput, WhatIfState } from '../types';
import { cn } from '../utils/cn';
import { formatCurrency, formatPercent } from '../utils/format';

interface FormState {
  actionId: string;
  actionCost: number;
  successPercent: number;
  probabilityPercent: number;
  clv: number;
}

const inputClass = 'field';

function StateCard({ title, state, highlight, currency }: { title: string; state: WhatIfState; highlight?: boolean; currency: string }) {
  return (
    <div className={cn('rounded-xl border p-4', highlight ? 'border-brand-300 bg-brand-50' : 'border-slate-200 bg-surface')}>
      <h3 className="text-sm font-semibold text-slate-900">{title}</h3>
      <dl className="mt-3 space-y-1.5 text-sm">
        {[
          ['Churn probability', formatPercent(state.churnProbability)],
          ['CLV', formatCurrency(state.clv, currency)],
          ['VaR', formatCurrency(state.valueAtRisk, currency)],
          ['Action', state.actionName],
          ['Action cost', formatCurrency(state.actionCost, currency)],
          ['Success rate', formatPercent(state.successRate, 0)],
        ].map(([k, v]) => (
          <div key={k} className="flex justify-between gap-3">
            <dt className="text-slate-500">{k}</dt>
            <dd className="text-right font-medium tabular-nums">{v}</dd>
          </div>
        ))}
      </dl>
    </div>
  );
}

export function WhatIfPage() {
  const service = useService();
  const [params] = useSearchParams();
  const requested = params.get('customer');

  const customers = useAsync(
    () => service.listCustomers({ sortBy: 'customerId', sortDirection: 'asc', pageSize: 500 }),
    [service],
  );
  const actions = useAsync(() => service.getActions(), [service]);

  const [customerId, setCustomerId] = useState<string>(requested ?? '');
  const [form, setForm] = useState<FormState | null>(null);
  const [submitted, setSubmitted] = useState<WhatIfInput | null>(null);

  // Default to the first customer once the list is available.
  const firstId = customers.data?.items[0]?.prediction.customerId ?? '';
  useEffect(() => {
    if (customerId === '' && firstId !== '') setCustomerId(firstId);
  }, [customerId, firstId]);

  const selected = useAsync(
    () => (customerId ? service.getCustomer(customerId) : Promise.resolve(null)),
    [service, customerId],
  );

  const catalogue = actions.data;
  const selectedData = selected.data;

  // Reset the form to the customer's current values whenever the customer changes.
  useEffect(() => {
    if (!selectedData || !catalogue || catalogue.length === 0) return;
    const action = selectedData.business.bestAction ?? selectedData.business.actionOptions[0].action;
    const initial: FormState = {
      actionId: action.id,
      actionCost: action.cost,
      successPercent: Math.round(action.successRate * 100),
      probabilityPercent: Math.round(selectedData.prediction.churnProbability * 100),
      clv: selectedData.business.clv,
    };
    setForm(initial);
    setSubmitted(toInput(selectedData.prediction.customerId, initial));
  }, [selectedData, catalogue]);

  const result = useAsync(
    () => (submitted ? service.runWhatIf(submitted) : Promise.resolve(null)),
    [service, submitted],
  );

  const pickAction = (action: RetentionAction | undefined) => {
    if (!action) return;
    setForm((f) => (f ? { ...f, actionId: action.id, actionCost: action.cost, successPercent: Math.round(action.successRate * 100) } : f));
  };

  const valid =
    form !== null &&
    Number.isFinite(form.actionCost) && form.actionCost >= 0 &&
    Number.isFinite(form.clv) && form.clv >= 0 &&
    form.successPercent >= 0 && form.successPercent <= 100 &&
    form.probabilityPercent >= 0 && form.probabilityPercent <= 100;

  const loadError = customers.status === 'error' ? customers : actions.status === 'error' ? actions : selected.status === 'error' ? selected : null;

  return (
    <>
      <PageHeader
        title="What-if Analysis"
        description="Explore how different business assumptions change the expected net benefit and the intervention decision for one customer."
        actions={
          <span className="inline-flex items-center gap-1.5 rounded-full bg-amber-100 px-3 py-1 text-xs font-semibold text-amber-900">
            <FlaskConical className="h-4 w-4" aria-hidden="true" />
            Scenario / What-if analysis
          </span>
        }
      />
      <p className="mb-6 rounded-lg bg-slate-100 px-4 py-3 text-sm text-slate-700">
        This is a business-scenario simulation. Changing the values below does not retrain or alter the churn model, and
        it does not change any stored customer data.
      </p>

      {loadError ? (
        <ErrorState message={loadError.error?.message} onRetry={loadError.reload} />
      ) : !customers.data || !form || !catalogue ? (
        <LoadingSkeleton variant="page" />
      ) : (
        <div className="grid gap-6 lg:grid-cols-3">
          <Card title="Scenario inputs" className="lg:col-span-1">
            <form
              className="space-y-4"
              onSubmit={(event) => {
                event.preventDefault();
                if (valid && selectedData) setSubmitted(toInput(selectedData.prediction.customerId, form));
              }}
            >
              <div>
                <label htmlFor="wi-customer" className="field-label">Customer</label>
                <select id="wi-customer" className={inputClass} value={customerId} onChange={(e) => setCustomerId(e.target.value)}>
                  {customers.data.items.map((c) => (
                    <option key={c.prediction.customerId} value={c.prediction.customerId}>
                      {c.prediction.customerId}
                    </option>
                  ))}
                </select>
              </div>
              <div>
                <label htmlFor="wi-action" className="field-label">Action</label>
                <select
                  id="wi-action"
                  className={inputClass}
                  value={form.actionId}
                  onChange={(e) => pickAction(catalogue.find((a) => a.id === e.target.value))}
                >
                  {catalogue.map((a) => (
                    <option key={a.id} value={a.id}>{a.name}</option>
                  ))}
                </select>
              </div>
              <div>
                <label htmlFor="wi-cost" className="field-label">Action cost ({selectedData?.business.currency ?? "USD"})</label>
                <input id="wi-cost" type="number" min={0} step={5} className={inputClass} value={form.actionCost}
                  onChange={(e) => setForm({ ...form, actionCost: e.target.valueAsNumber })} />
              </div>
              <div>
                <label htmlFor="wi-success" className="field-label">
                  Action success rate: {Number.isFinite(form.successPercent) ? form.successPercent : 0}%
                </label>
                <input id="wi-success" type="range" min={0} max={100} step={1} className="w-full" value={form.successPercent}
                  onChange={(e) => setForm({ ...form, successPercent: e.target.valueAsNumber })} />
              </div>
              <div>
                <label htmlFor="wi-prob" className="field-label">
                  Churn probability scenario: {Number.isFinite(form.probabilityPercent) ? form.probabilityPercent : 0}%
                </label>
                <input id="wi-prob" type="range" min={0} max={100} step={1} className="w-full" value={form.probabilityPercent}
                  onChange={(e) => setForm({ ...form, probabilityPercent: e.target.valueAsNumber })} />
              </div>
              <div>
                <label htmlFor="wi-clv" className="field-label">CLV scenario ({selectedData?.business.currency ?? "USD"})</label>
                <input id="wi-clv" type="number" min={0} step="any" className={inputClass} value={form.clv}
                  onChange={(e) => setForm({ ...form, clv: e.target.valueAsNumber })} />
              </div>
              <button
                type="submit"
                disabled={!valid}
                className="w-full btn btn-primary disabled:cursor-not-allowed disabled:opacity-50"
              >
                Run scenario
              </button>
              {!valid && <p className="text-xs text-rose-700">Enter non-negative numbers; percentages must be between 0 and 100.</p>}
            </form>
          </Card>

          <div className="lg:col-span-2">
            <AsyncBoundary
              state={result}
              skeleton={<LoadingSkeleton variant="card" />}
              errorTitle="Unable to run the scenario."
            >
              {(r) =>
                r && (
                  <div className="space-y-4">
                    <div className="flex flex-col items-stretch gap-3 md:flex-row md:items-center">
                      <div className="flex-1"><StateCard title="Current State" state={r.current} currency={selectedData?.business.currency ?? "USD"} /></div>
                      <ArrowRight className="hidden h-5 w-5 shrink-0 text-slate-400 md:block" aria-hidden="true" />
                      <ArrowDown className="mx-auto h-5 w-5 text-slate-400 md:hidden" aria-hidden="true" />
                      <div className="flex-1"><StateCard title="Scenario" state={r.scenario} highlight currency={selectedData?.business.currency ?? "USD"} /></div>
                    </div>
                    <ArrowDown className="mx-auto h-5 w-5 text-slate-400" aria-hidden="true" />
                    <div className="grid gap-4 sm:grid-cols-2">
                      <div className="rounded-xl border border-slate-200 bg-surface p-4">
                        <h3 className="text-sm font-semibold text-slate-900">New ENB</h3>
                        <p className={cn('mt-2 text-3xl font-bold tabular-nums', r.scenario.expectedNetBenefit < 0 ? 'text-rose-700' : 'text-emerald-700')}>
                          {formatCurrency(r.scenario.expectedNetBenefit, selectedData?.business.currency ?? 'USD')}
                        </p>
                        <p className="mt-1 text-xs text-slate-600">
                          {r.deltaEnb >= 0 ? '+' : '−'}{formatCurrency(Math.abs(r.deltaEnb), selectedData?.business.currency ?? 'USD')} vs current ({formatCurrency(r.current.expectedNetBenefit, selectedData?.business.currency ?? 'USD')})
                        </p>
                      </div>
                      <div className="rounded-xl border border-slate-200 bg-surface p-4">
                        <h3 className="text-sm font-semibold text-slate-900">Decision</h3>
                        <div className="mt-3"><DecisionBadge decision={r.scenario.decision} /></div>
                        <p className="mt-2 text-xs text-slate-600">
                          Current decision: {r.current.decision}
                        </p>
                      </div>
                    </div>
                    <p className="text-xs text-slate-500">{r.label} · customer {r.customerId}</p>
                  </div>
                )
              }
            </AsyncBoundary>
          </div>
        </div>
      )}
    </>
  );
}

function toInput(customerId: string, f: FormState): WhatIfInput {
  return {
    customerId,
    actionId: f.actionId,
    actionCost: f.actionCost,
    successRate: f.successPercent / 100,
    churnProbability: f.probabilityPercent / 100,
    clv: f.clv,
  };
}
