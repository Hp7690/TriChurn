import { useState } from 'react';
import { BarChart, Histogram } from '../../components/revenue/charts';
import { formatMoney, formatNumber, formatPercent } from '../../components/revenue/format';
import { AsyncView, DataTable, EmptyState, KpiCard, Notice, PageIntro, Pagination, Panel, StatusBadge, WarningList } from '../../components/revenue/primitives';
import { useAsync } from '../../components/revenue/useAsync';
import { useRevenue } from '../../services/revenue';
import type { ClvCustomerQuery } from '../../types/revenue';

const SEGMENTS = ['Low Value', 'Medium Value', 'High Value', 'Premium Value', 'Unassigned'];

export function ClvPage() {
  const api = useRevenue();
  const summary = useAsync(() => api.clvSummary(), [api]);
  const segments = useAsync(() => api.clvSegments(), [api]);
  const [query, setQuery] = useState<ClvCustomerQuery>({ page: 1, page_size: 20, sort_by: 'observed_billing', descending: true });
  const customers = useAsync(() => api.clvCustomers(query), [api, query]);

  return (
    <div className="space-y-6">
      <PageIntro title="Customer Lifetime Value" description="Observed billing is a PROXY for value delivered to date. Scenario CLV adds assumed future recurring billing and is not a forecast." />
      <AsyncView state={summary} label="Loading CLV summary">
        {(s) => (
          <>
            <div className="grid gap-4 sm:grid-cols-2 xl:grid-cols-3">{s.metrics.map((m) => <KpiCard key={m.key} metric={m} />)}</div>
            <Panel title="Scenario assumptions" badge={<StatusBadge status={s.scenario.status} />} subtitle="Configured business assumptions, not measured facts.">
              {s.scenario.status === 'UNAVAILABLE' ? (
                <Notice tone="warn">{s.scenario.reason}</Notice>
              ) : (
                <>
                  <ul className="list-disc pl-5 text-sm text-slate-700">
                    {Object.entries(s.scenario.remaining_months_by_contract).map(([k, v]) => <li key={k}>{k}: {v} assumed remaining months</li>)}
                    <li>Monthly discount rate: {s.scenario.monthly_discount_rate}</li>
                  </ul>
                  {!s.scenario.assumptions_confirmed ? <div className="mt-2"><Notice tone="warn">Assumptions are unconfirmed defaults, so scenario values are Illustrative and must not drive decisions.</Notice></div> : null}
                </>
              )}
            </Panel>
            <Panel title="Observed billing distribution" badge={<StatusBadge status={s.distribution_status} />} subtitle="Equal-width bins of TotalCharges (valid values only).">
              <Histogram bins={s.distribution_observed_billing} title="Observed billing distribution" xLabel="Observed cumulative billing (currency units)" />
              <p className="mt-2 text-xs text-slate-600">
                {formatNumber(s.customers_without_valid_billing)} customers have no valid TotalCharges (excluded, not counted as zero);{' '}
                {formatNumber(s.customers_with_inconsistent_billing)} have billing inconsistent with monthly charges × tenure (flagged, not corrected).
              </p>
            </Panel>
          </>
        )}
      </AsyncView>
      <AsyncView state={segments} label="Loading segments">
        {(g) => (
          <Panel title="Value segments" badge={<StatusBadge status={g.metric_status} />} subtitle={`${g.note} Metric: ${g.metric}; method: ${g.method}.`}>
            {g.reason ? <Notice tone="warn">{g.reason}</Notice> : null}
            {g.thresholds ? <p className="mb-2 text-xs text-slate-600">Thresholds: {g.thresholds.map((t) => formatMoney(t)).join(' / ')}</p> : null}
            <BarChart title="Customers by value segment" valueLabel="customers" data={g.segments.map((x) => ({ label: x.segment, value: x.customers }))} format={(v) => formatNumber(v)} />
            <div className="mt-4">
              <DataTable caption="Value segment summary" rows={g.segments} rowKey={(r) => r.segment}
                columns={[
                  { key: 's', header: 'Segment', render: (r) => r.segment },
                  { key: 'c', header: 'Customers', align: 'right', render: (r) => formatNumber(r.customers) },
                  { key: 'b', header: 'Observed billing', align: 'right', render: (r) => formatMoney(r.observed_billing_total) },
                  { key: 'a', header: 'Avg billing', align: 'right', render: (r) => formatMoney(r.avg_observed_billing) },
                  { key: 'e', header: 'Avg scenario CLV', align: 'right', render: (r) => formatMoney(r.avg_estimated_clv) },
                  { key: 'h', header: 'Churn label share', align: 'right', render: (r) => formatPercent(r.churn_rate) },
                ]} />
            </div>
          </Panel>
        )}
      </AsyncView>
      <Panel title="Customer CLV" subtitle="Paged. Billing values are ACTUAL observations; scenario values carry their own status.">
        <div className="mb-3 flex flex-wrap gap-3 text-sm">
          <label className="flex items-center gap-2">Segment
            <select aria-label="Segment filter" className="field w-auto !py-1" value={query.segment ?? ''}
              onChange={(e) => setQuery({ ...query, segment: e.target.value || undefined, page: 1 })}>
              <option value="">All</option>
              {SEGMENTS.map((x) => <option key={x} value={x}>{x}</option>)}
            </select>
          </label>
          <label className="flex items-center gap-2">Sort by
            <select aria-label="Sort by" className="field w-auto !py-1" value={query.sort_by}
              onChange={(e) => setQuery({ ...query, sort_by: e.target.value as ClvCustomerQuery['sort_by'], page: 1 })}>
              <option value="observed_billing">Observed billing</option>
              <option value="estimated_clv">Scenario CLV</option>
              <option value="monthly_charges">Monthly charges</option>
              <option value="tenure">Tenure</option>
              <option value="customer_id">Customer ID</option>
            </select>
          </label>
        </div>
        <AsyncView state={customers} label="Loading customers">
          {(p) => (
            <>
              <DataTable caption="Customer CLV" rows={p.items} rowKey={(r) => r.customer_id} empty={<EmptyState title="No customers match this filter." />}
                columns={[
                  { key: 'id', header: 'Customer', render: (r) => r.customer_id },
                  { key: 'seg', header: 'Segment', render: (r) => r.value_segment },
                  { key: 'mc', header: 'Monthly', align: 'right', render: (r) => formatMoney(r.monthly_charges) },
                  { key: 'ob', header: 'Observed billing', align: 'right', render: (r) => <>{formatMoney(r.observed_billing)} {r.observed_billing_status !== 'ACTUAL' ? <StatusBadge status={r.observed_billing_status} /> : null}</> },
                  { key: 'ec', header: 'Scenario CLV', align: 'right', render: (r) => <>{formatMoney(r.estimated_clv)} <StatusBadge status={r.estimated_clv_status} /></> },
                  { key: 'fl', header: 'Flags', render: (r) => (r.billing_inconsistent ? 'Billing inconsistent' : '') },
                ]} />
              <Pagination page={p.page} pageCount={p.page_count} total={p.total} onPage={(n) => setQuery({ ...query, page: n })} />
            </>
          )}
        </AsyncView>
      </Panel>
      <WarningList items={['Revenue is not profit: no acquisition, cost-to-serve or margin data exists.']} />
    </div>
  );
}
