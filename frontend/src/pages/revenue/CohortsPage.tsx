import { BarChart } from '../../components/revenue/charts';
import { formatMoney, formatNumber, formatPercent } from '../../components/revenue/format';
import { AsyncView, DataTable, Notice, PageIntro, Panel, StatusBadge, WarningList } from '../../components/revenue/primitives';
import { useAsync } from '../../components/revenue/useAsync';
import { useRevenue } from '../../services/revenue';
import type { CohortRow } from '../../types/revenue';

function CohortTable({ rows, caption }: { rows: CohortRow[]; caption: string }) {
  return (
    <DataTable caption={caption} rows={rows} rowKey={(r) => r.cohort}
      columns={[
        { key: 'c', header: 'Cohort', render: (r) => r.cohort },
        { key: 'n', header: 'Customers', align: 'right', render: (r) => formatNumber(r.customers) },
        { key: 'ch', header: 'Churn label share', align: 'right', render: (r) => formatPercent(r.churn_rate) },
        { key: 'm', header: 'Avg monthly', align: 'right', render: (r) => formatMoney(r.avg_monthly_charges) },
        { key: 'b', header: 'Avg observed billing', align: 'right', render: (r) => formatMoney(r.avg_observed_billing) },
        { key: 'v', header: 'Avg scenario CLV', align: 'right', render: (r) => formatMoney(r.avg_estimated_clv) },
      ]} />
  );
}

export function CohortsPage() {
  const api = useRevenue();
  const tenure = useAsync(() => api.cohortTenure(), [api]);
  const summary = useAsync(() => api.cohortSummary(), [api]);
  return (
    <div className="space-y-6">
      <PageIntro title="Cohort Analytics" description="Tenure-based proxy cohorts. These are not acquisition-month cohorts and show no calendar retention." />
      <AsyncView state={tenure} label="Loading cohorts">
        {(t) => (
          <>
            <Notice tone="warn">Method: {t.method}. {t.limitations.join(' ')}</Notice>
            <Panel title="Tenure buckets" badge={<StatusBadge status={t.status} />} subtitle="Months of tenure at snapshot time.">
              <BarChart title="Churn label share by tenure bucket" valueLabel="share of customers labelled churned" data={t.tenure_buckets.map((b) => ({ label: b.cohort, value: b.churn_rate, display: formatPercent(b.churn_rate) }))} />
              <div className="mt-4"><CohortTable rows={t.tenure_buckets} caption="Tenure buckets" /></div>
            </Panel>
            <Panel title="Customer value by tenure bucket" badge={<StatusBadge status="ACTUAL" />} subtitle="Average observed billing (valid TotalCharges only).">
              <BarChart title="Average observed billing by tenure bucket" valueLabel="currency units" data={t.tenure_buckets.map((b) => ({ label: b.cohort, value: b.avg_observed_billing }))} format={(v) => formatMoney(v)} />
            </Panel>
            <Panel title="Lifecycle groups" badge={<StatusBadge status={t.status} />}><CohortTable rows={t.lifecycle_groups} caption="Lifecycle groups" /></Panel>
            <Panel title="Contract cohorts" badge={<StatusBadge status="ACTUAL" />}><CohortTable rows={t.contract_cohorts} caption="Contract cohorts" /></Panel>
          </>
        )}
      </AsyncView>
      <AsyncView state={summary} label="Loading cohort availability">
        {(s) => (
          <Panel title="Not supported without additional data" badge={<StatusBadge status="BLOCKED_BY_MISSING_DATA" />} subtitle="No signup dates or dated revenue exist in the snapshot, so nothing below is fabricated.">
            <ul className="space-y-2 text-sm">
              {s.blocked_by_missing_data.map((b) => (
                <li key={b.analysis} className="flex flex-wrap items-center gap-2"><StatusBadge status={b.status} /><span className="font-medium">{b.analysis.replace(/_/g, ' ')}</span><span className="text-slate-600">{b.reason}</span></li>
              ))}
            </ul>
            <WarningList items={[s.acquisition_cohorts.reason ?? '']} />
          </Panel>
        )}
      </AsyncView>
    </div>
  );
}
