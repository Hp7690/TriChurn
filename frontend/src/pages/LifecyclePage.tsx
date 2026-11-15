import { Layers, Percent, ShieldQuestion, Users } from 'lucide-react';
import { LifecycleChurnChart, LifecycleContractChart, LifecycleCustomersChart } from '../charts/LifecycleCharts';
import { AsyncBoundary } from '../components/AsyncBoundary';
import { Card } from '../components/Card';
import { EmptyState } from '../components/EmptyState';
import { ExperienceStatusBadge } from '../components/ExperienceStatusBadge';
import { KpiCard } from '../components/KpiCard';
import { PageHeader } from '../components/PageHeader';
import { useAsync } from '../hooks/useAsync';
import { experienceApi, type ExperienceApi } from '../services/experienceService';
import type { LifecycleGroup, LifecycleResponse } from '../types/experience';
import { formatNumber } from '../utils/format';

const fixed = (v: number | null | undefined): string => (v == null ? '—' : v.toLocaleString('en-US', { maximumFractionDigits: 2 }));
const range = (g: { min_months: number; max_months: number | null }): string =>
  g.max_months === null ? `${g.min_months}+ months` : `${g.min_months}–${g.max_months - 1} months`;

function GroupTable({ groups }: { groups: LifecycleGroup[] }) {
  return (
    <div className="overflow-x-auto">
      <table className="w-full min-w-[56rem] text-left text-sm">
        <caption className="sr-only">Lifecycle group statistics</caption>
        <thead className="text-xs text-slate-500">
          <tr>
            {['Group', 'Tenure', 'Customers', 'Share', 'Churned (actual)', 'Observed churn rate', 'Avg monthly charge', 'Median monthly charge', 'Avg total charge', 'Missing total'].map((h) => (
              <th key={h} scope="col" className="py-2 pr-3 font-semibold">{h}</th>
            ))}
          </tr>
        </thead>
        <tbody className="divide-y divide-slate-100">
          {groups.map((g) => (
            <tr key={g.name}>
              <th scope="row" className="py-2 pr-3 font-medium text-slate-900">{g.name}</th>
              <td className="py-2 pr-3 text-slate-600">{range(g)}</td>
              <td className="py-2 pr-3 tabular-nums">{formatNumber(g.customers)}</td>
              <td className="py-2 pr-3 tabular-nums">{g.share_pct == null ? '—' : `${g.share_pct}%`}</td>
              <td className="py-2 pr-3 tabular-nums">{g.churn ? formatNumber(g.churn.churned) : '—'}</td>
              <td className="py-2 pr-3 tabular-nums">
                {g.churn?.churn_rate_pct != null ? (
                  `${g.churn.churn_rate_pct}%`
                ) : (
                  <span title={g.churn?.rate_withheld_reason ?? 'No churn labels in the dataset.'} className="text-slate-500">
                    Withheld
                  </span>
                )}
              </td>
              <td className="py-2 pr-3 tabular-nums">{fixed(g.monthly_charges?.mean)}</td>
              <td className="py-2 pr-3 tabular-nums">{fixed(g.monthly_charges?.median)}</td>
              <td className="py-2 pr-3 tabular-nums">{fixed(g.total_charges?.mean)}</td>
              <td className="py-2 tabular-nums">{g.total_charges?.missing ?? '—'}</td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}

function RiskCard({ data }: { data: LifecycleResponse }) {
  const risk = data.risk_distribution;
  if (!risk || risk.status !== 'AVAILABLE' || !risk.bands) {
    return (
      <Card title="Lifecycle risk distribution" actions={<ExperienceStatusBadge status={risk?.status ?? 'BLOCKED_BY_MISSING_DATA'} />}>
        <p className="text-sm text-slate-700">
          {risk?.reason ?? 'No existing churn probabilities are available.'} Probabilities are never re-predicted or estimated here.
        </p>
      </Card>
    );
  }
  const bands = risk.bands;
  return (
    <Card title="Lifecycle risk distribution" description={risk.note} actions={<ExperienceStatusBadge status={risk.status} />}>
      <dl className="grid grid-cols-3 gap-3">
        {(['LOW', 'MEDIUM', 'HIGH'] as const).map((b) => (
          <div key={b}>
            <dt className="text-xs text-slate-500">{b} risk</dt>
            <dd className="text-xl font-semibold tabular-nums">{formatNumber(bands[b])}</dd>
          </div>
        ))}
      </dl>
      <p className="mt-2 text-xs text-slate-500">
        Source: {risk.source}. Customers without a valid probability: {formatNumber(risk.missing_probability ?? 0)}.
      </p>
    </Card>
  );
}

function LifecycleBody({ data }: { data: LifecycleResponse }) {
  if (data.customers_analysed === 0) {
    return (
      <EmptyState
        title={data.status === 'DISABLED' ? 'Lifecycle module is disabled' : 'Lifecycle analysis unavailable'}
        description={data.reason ?? 'No customer rows with a valid tenure were found.'}
        action={<ExperienceStatusBadge status={data.status} />}
      />
    );
  }
  const overallRate = data.overall?.churn_rate_pct;
  return (
    <div className="space-y-6">
      <div className="grid gap-4 sm:grid-cols-2 lg:grid-cols-4">
        <KpiCard label="Customers analysed" value={formatNumber(data.customers_analysed)} hint={`of ${formatNumber(data.customers_total)} rows`} icon={Users} tone="brand" />
        <KpiCard label="Lifecycle groups" value={String(data.groups.length)} hint="configured tenure thresholds" icon={Layers} />
        <KpiCard
          label="Observed churn rate"
          value={overallRate == null ? 'n/a' : `${overallRate}%`}
          hint="actual Churn labels, not a prediction"
          icon={Percent}
          tone="danger"
        />
        <KpiCard label="Excluded rows" value={formatNumber(data.excluded.total)} hint="missing or invalid tenure" icon={ShieldQuestion} />
      </div>
      <div className="grid gap-4 lg:grid-cols-2">
        <Card title="Customers by lifecycle group"><LifecycleCustomersChart groups={data.groups} /></Card>
        <Card title="Observed churn rate by group" description="Actual labels. Groups below the minimum size are withheld.">
          <LifecycleChurnChart groups={data.groups} />
        </Card>
      </div>
      <Card title="Contract mix by group"><LifecycleContractChart groups={data.groups} /></Card>
      <Card title="Group statistics" description="Charges are billing amounts as recorded (currency not specified); they are not profit or lifetime value.">
        <GroupTable groups={data.groups} />
      </Card>
      <RiskCard data={data} />
      <Card title="Methodology, assumptions and limitations">
        <p className="text-sm text-slate-700">{data.methodology}</p>
        <div className="mt-4 grid gap-4 md:grid-cols-2">
          <div>
            <h3 className="text-sm font-semibold text-slate-900">Thresholds (months)</h3>
            <ul className="mt-1 list-disc pl-5 text-sm text-slate-700">
              {data.thresholds.map((t) => (<li key={t.name}>{t.name}: {range(t)}</li>))}
            </ul>
            <h3 className="mt-3 text-sm font-semibold text-slate-900">Assumptions</h3>
            <ul className="mt-1 list-disc pl-5 text-sm text-slate-700">{data.assumptions.map((a) => (<li key={a}>{a}</li>))}</ul>
          </div>
          <div>
            <h3 className="text-sm font-semibold text-slate-900">Limitations</h3>
            <ul className="mt-1 list-disc pl-5 text-sm text-slate-700">{data.limitations.map((a) => (<li key={a}>{a}</li>))}</ul>
            <p className="mt-3 text-xs text-slate-500">
              Columns used: {data.columns_used.join(', ') || 'none'}.
              {data.columns_missing.length > 0 && ` Not in the dataset: ${data.columns_missing.join(', ')}.`}
            </p>
            <p className="mt-1 text-xs text-slate-500">{data.source} · generated {data.generated_at}</p>
          </div>
        </div>
      </Card>
    </div>
  );
}

export function LifecyclePage({ api = experienceApi }: { api?: ExperienceApi }) {
  const state = useAsync(() => api.getLifecycle(), [api]);
  return (
    <>
      <PageHeader
        title="Customer Lifecycle"
        description="Customers grouped by tenure. This is a tenure-based lifecycle proxy, not an event-based customer journey."
        actions={<span className="rounded-full bg-amber-100 px-3 py-1 text-xs font-semibold text-amber-900">TENURE PROXY</span>}
      />
      <AsyncBoundary state={state} errorTitle="Unable to load the lifecycle analysis.">
        {(data) => <LifecycleBody data={data} />}
      </AsyncBoundary>
    </>
  );
}
