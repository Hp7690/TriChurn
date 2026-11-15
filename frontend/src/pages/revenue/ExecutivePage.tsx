import { BarChart, Histogram } from '../../components/revenue/charts';
import { formatMoney, formatNumber, formatPercent, titleCase } from '../../components/revenue/format';
import { AsyncView, DataTable, KpiCard, Notice, PageIntro, Panel, StatusBadge, WarningList } from '../../components/revenue/primitives';
import { useAsync } from '../../components/revenue/useAsync';
import { useRevenue } from '../../services/revenue';

export function ExecutivePage() {
  const api = useRevenue();
  const summary = useAsync(() => api.summary(), [api]);
  const clv = useAsync(() => api.clvSummary(), [api]);
  const availability = useAsync(() => api.availability(), [api]);

  return (
    <div className="space-y-6">
      <PageIntro title="Executive Revenue Dashboard" description="One view of customer value, exposure and opportunity, with the evidence status of every number." />
      <AsyncView state={summary} label="Loading executive summary">
        {(s) => (
          <>
            <section aria-label="Customer value overview">
              <h2 className="mb-2 text-sm font-semibold text-slate-700">1 · Customer value overview</h2>
              <div className="grid gap-4 sm:grid-cols-2 xl:grid-cols-4">{s.headline_metrics.map((m) => <KpiCard key={m.key} metric={m} />)}</div>
            </section>
            <Panel title="3 · Revenue at risk (rule-flagged, unweighted)" badge={<StatusBadge status="PROXY" />} subtitle="Flagged active customers by contract. Not lost and not recoverable revenue.">
              <BarChart title="Flagged customers by contract" valueLabel="customers" data={s.risk.by_contract.map((r) => ({ label: r.group, value: r.flagged_customers }))} format={(v) => formatNumber(v)} />
            </Panel>
            <Panel title="4 · Recurring monthly charges exposure" badge={<StatusBadge status="PROXY" />} subtitle="Flagged monthly charges by tenure group (currency units / month).">
              <BarChart title="Flagged monthly exposure by tenure group" valueLabel="currency units / month" data={s.risk.by_tenure_group.map((r) => ({ label: r.group, value: r.flagged_monthly_exposure }))} format={(v) => formatMoney(v)} />
            </Panel>
            <Panel title="5 · Customer value segments" badge={<StatusBadge status="ACTUAL" />} subtitle="Business value tiers (not Phase 5 ML segments).">
              <BarChart title="Observed billing share by segment" valueLabel="share of observed billing" data={s.clv.segments.map((x) => ({ label: x.segment, value: x.observed_billing_share, display: formatPercent(x.observed_billing_share) }))} />
            </Panel>
            <Panel title="6 · Upsell / cross-sell opportunities" badge={<StatusBadge status="PROXY" />} subtitle="Advisory and human-reviewed. No uplift is estimated.">
              <BarChart title="Eligible opportunities by type" valueLabel="recommendations" data={Object.entries(s.opportunities.by_type).map(([k, v]) => ({ label: titleCase(k), value: v }))} format={(v) => formatNumber(v)} />
            </Panel>
            <Panel title="7 · Tenure cohort analysis" badge={<StatusBadge status="PROXY" />} subtitle="TENURE_BASED_PROXY, not acquisition cohorts.">
              <BarChart title="Churn label share by tenure bucket" valueLabel="share" data={s.cohorts.map((c) => ({ label: c.cohort, value: c.churn_rate, display: formatPercent(c.churn_rate) }))} />
            </Panel>
            <Panel title="8 · Revenue forecasting readiness" badge={<StatusBadge status={s.forecast_state === 'FORECAST_READY' ? 'ACTUAL' : 'BLOCKED_BY_MISSING_DATA'} />}>
              <p className="font-mono text-sm font-semibold" data-testid="exec-forecast-state">{s.forecast_state}</p>
              {s.forecast_state !== 'FORECAST_READY' ? <p className="mt-1 text-sm text-slate-600">No time-indexed revenue history is available, so no forecast is produced.</p> : null}
            </Panel>
            <WarningList items={s.warnings} />
          </>
        )}
      </AsyncView>
      <Panel title="2 · CLV distribution" badge={<StatusBadge status="ACTUAL" />} subtitle="Observed cumulative billing per customer.">
        <AsyncView state={clv} label="Loading CLV distribution">
          {(c) => <Histogram bins={c.distribution_observed_billing} title="Observed billing distribution" xLabel="Observed cumulative billing (currency units)" />}
        </AsyncView>
      </Panel>
      <AsyncView state={availability} label="Loading data availability">
        {(a) => (
          <>
            <Panel title="9 · Data quality and availability">
              <DataTable caption="Module availability" rows={a.modules} rowKey={(m) => m.module}
                columns={[{ key: 'm', header: 'Module', render: (m) => m.module }, { key: 's', header: 'Status', render: (m) => <StatusBadge status={m.status} /> }, { key: 'd', header: 'Detail', render: (m) => m.detail }]} />
              <p className="mt-3 text-sm text-slate-700">
                {formatNumber(a.data_quality.rows_used)} of {formatNumber(a.data_quality.rows_read)} rows used · {formatNumber(a.data_quality.duplicate_ids_dropped)} duplicate IDs dropped ·{' '}
                {formatNumber(a.data_quality.missing_total_charges + a.data_quality.invalid_total_charges)} rows without valid TotalCharges · {formatNumber(a.data_quality.inconsistent_total_vs_monthly)} inconsistent billing rows.
              </p>
              {a.data_quality.notes.map((n) => <Notice key={n} tone="warn">{n}</Notice>)}
            </Panel>
            <Panel title="10 · Business assumptions and metric definitions" subtitle="Same definitions the API uses.">
              <ul className="divide-y divide-slate-100 text-sm">
                {a.metric_definitions.map((d) => (
                  <li key={d.key} className="py-2">
                    <details>
                      <summary className="cursor-pointer font-medium">{d.name} <StatusBadge status={d.default_status} /></summary>
                      <p className="mt-1 text-slate-700">{d.description}</p>
                      <p className="mt-1"><span className="font-semibold">Formula: </span>{d.formula}</p>
                      <p><span className="font-semibold">Fields: </span>{d.source_fields.join(', ')}</p>
                      {d.assumptions.length ? <p><span className="font-semibold">Assumptions: </span>{d.assumptions.join(' ')}</p> : null}
                      {d.limitations.length ? <p><span className="font-semibold">Limitations: </span>{d.limitations.join(' ')}</p> : null}
                    </details>
                  </li>
                ))}
              </ul>
            </Panel>
          </>
        )}
      </AsyncView>
    </div>
  );
}
