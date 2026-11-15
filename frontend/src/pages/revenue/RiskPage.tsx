import { useState } from 'react';
import { BarChart } from '../../components/revenue/charts';
import { formatMoney, formatNumber, formatPercent } from '../../components/revenue/format';
import { AsyncView, DataTable, EmptyState, KpiCard, Notice, PageIntro, Pagination, Panel, StatusBadge, WarningList } from '../../components/revenue/primitives';
import { useAsync } from '../../components/revenue/useAsync';
import { useRevenue } from '../../services/revenue';
import type { RiskGroupRow } from '../../types/revenue';

type GroupKey = 'by_contract' | 'by_tenure_group' | 'by_value_segment';
const GROUPS: Array<{ key: GroupKey; label: string }> = [
  { key: 'by_contract', label: 'Contract type' },
  { key: 'by_tenure_group', label: 'Tenure group' },
  { key: 'by_value_segment', label: 'Value segment' },
];

function GroupTable({ rows }: { rows: RiskGroupRow[] }) {
  return (
    <DataTable caption="Exposure by group" rows={rows} rowKey={(r) => r.group}
      columns={[
        { key: 'g', header: 'Group', render: (r) => r.group },
        { key: 'a', header: 'Active', align: 'right', render: (r) => formatNumber(r.active_customers) },
        { key: 'f', header: 'Rule-flagged', align: 'right', render: (r) => formatNumber(r.flagged_customers) },
        { key: 's', header: 'Share of active', align: 'right', render: (r) => formatPercent(r.flagged_share_of_active) },
        { key: 'm', header: 'Flagged monthly (unweighted)', align: 'right', render: (r) => formatMoney(r.flagged_monthly_exposure) },
        { key: 'e', header: 'Probability-weighted', align: 'right', render: (r) => formatMoney(r.expected_monthly_exposure) },
        { key: 'c', header: 'Already churned (context)', align: 'right', render: (r) => formatMoney(r.churned_monthly_context) },
      ]} />
  );
}

export function RiskPage() {
  const api = useRevenue();
  const summary = useAsync(() => api.riskSummary(), [api]);
  const [group, setGroup] = useState<GroupKey>('by_contract');
  const [page, setPage] = useState(1);
  const customers = useAsync(() => api.riskCustomers({ page, page_size: 20 }), [api, page]);

  return (
    <div className="space-y-6">
      <PageIntro title="Revenue at Risk" description="Exposure is a screening view, not a prediction. Exposed revenue is not lost revenue and not guaranteed recoverable revenue." />
      <AsyncView state={summary} label="Loading revenue exposure">
        {(s) => {
          const byKey = Object.fromEntries(s.metrics.map((m) => [m.key, m]));
          const rows = s[group];
          return (
            <>
              <section aria-label="Exposure views" className="grid gap-4 lg:grid-cols-3">
                <div>
                  <h2 className="mb-2 text-sm font-semibold text-slate-700">1 · Historical context (already churned)</h2>
                  <div className="space-y-3">
                    {byKey.churned_monthly_context ? <KpiCard metric={byKey.churned_monthly_context} /> : null}
                    {byKey.churned_billing_context ? <KpiCard metric={byKey.churned_billing_context} /> : null}
                  </div>
                </div>
                <div>
                  <h2 className="mb-2 text-sm font-semibold text-slate-700">2 · Rule-flagged exposure (active customers)</h2>
                  <div className="space-y-3">
                    {byKey.rule_flagged_monthly_exposure ? <KpiCard metric={byKey.rule_flagged_monthly_exposure} /> : null}
                    {byKey.rule_flagged_billing_exposure ? <KpiCard metric={byKey.rule_flagged_billing_exposure} /> : null}
                  </div>
                </div>
                <div>
                  <h2 className="mb-2 text-sm font-semibold text-slate-700">3 · Probability-weighted exposure</h2>
                  {byKey.expected_monthly_exposure ? <KpiCard metric={byKey.expected_monthly_exposure} /> : null}
                  {!s.probability_weighting.available ? <div className="mt-3"><Notice tone="info">{s.probability_weighting.reason}</Notice></div> : null}
                </div>
              </section>
              <Panel title="Rule definition" badge={<StatusBadge status={s.rule_definition.status} />} subtitle="Screening indicators, not a probability.">
                <p className="text-sm text-slate-700">
                  A currently active customer is flagged when at least {s.rule_definition.min_indicators_to_flag} indicators match:{' '}
                  {Object.entries(s.rule_definition.indicators).map(([k, v]) => `${k.replace(/_/g, ' ')} (${String(v)})`).join(', ')}.
                </p>
                <p className="mt-1 text-sm text-slate-700">{formatNumber(s.flagged_customers)} of {formatNumber(s.active_customers)} active customers are flagged.</p>
              </Panel>
              <Panel title="Exposure by group" subtitle="Flagged recurring monthly charges (PROXY, unweighted).">
                <div role="tablist" aria-label="Group by" className="mb-3 flex gap-2">
                  {GROUPS.map((g) => (
                    <button key={g.key} role="tab" type="button" aria-selected={group === g.key} onClick={() => setGroup(g.key)}
                      className={`rounded-md px-3 py-1 text-sm ${group === g.key ? 'bg-brand-600 text-white' : 'border border-slate-300 text-slate-700'}`}>{g.label}</button>
                  ))}
                </div>
                <BarChart title="Flagged monthly exposure" valueLabel="currency units / month" data={rows.map((r) => ({ label: r.group, value: r.flagged_monthly_exposure }))} format={(v) => formatMoney(v)} />
                <div className="mt-4"><GroupTable rows={rows} /></div>
              </Panel>
              <WarningList items={s.warnings} />
            </>
          );
        }}
      </AsyncView>
      <Panel title="Rule-flagged customers" subtitle="Sorted by monthly charges. Exposure basis: rule-flagged, unweighted (Proxy).">
        <AsyncView state={customers} label="Loading customers">
          {(p) => (
            <>
              <DataTable caption="Rule-flagged customers" rows={p.items} rowKey={(r) => r.customer_id} empty={<EmptyState title="No customers are rule-flagged." />}
                columns={[
                  { key: 'id', header: 'Customer', render: (r) => r.customer_id },
                  { key: 'c', header: 'Contract', render: (r) => r.contract ?? 'Unavailable' },
                  { key: 't', header: 'Tenure group', render: (r) => r.tenure_group },
                  { key: 'm', header: 'Monthly', align: 'right', render: (r) => formatMoney(r.monthly_charges) },
                  { key: 'i', header: 'Indicators', render: (r) => r.indicators.map((i) => i.replace(/_/g, ' ')).join(', ') },
                  { key: 'p', header: 'Churn probability', render: (r) => (r.churn_probability === null ? 'Unavailable' : formatPercent(r.churn_probability)) },
                  { key: 's', header: 'Status', render: (r) => <StatusBadge status={r.exposure_status} /> },
                ]} />
              <Pagination page={p.page} pageCount={p.page_count} total={p.total} onPage={setPage} />
            </>
          )}
        </AsyncView>
      </Panel>
    </div>
  );
}
