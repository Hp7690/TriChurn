import { Fragment, useState } from 'react';
import { BarChart } from '../../components/revenue/charts';
import { formatNumber, titleCase } from '../../components/revenue/format';
import { AsyncView, EmptyState, KpiCard, Notice, PageIntro, Pagination, Panel, StatusBadge, WarningList } from '../../components/revenue/primitives';
import { useAsync } from '../../components/revenue/useAsync';
import { useRevenue } from '../../services/revenue';
import type { Opportunity, OpportunityQuery } from '../../types/revenue';

const TYPES = ['SERVICE_ADDON_CROSS_SELL', 'STREAMING_CROSS_SELL', 'PROTECTION_BUNDLE_REVIEW', 'CONTRACT_TERM_REVIEW'];
const ELIGIBILITY = ['ELIGIBLE', 'INELIGIBLE_ALREADY_CHURNED', 'INELIGIBLE_NO_INTERNET_SERVICE', 'INELIGIBLE_INSUFFICIENT_DATA'];

function Explanation({ o }: { o: Opportunity }) {
  return (
    <div className="rounded-md bg-slate-50 p-3 text-sm text-slate-800" data-testid={`explain-${o.customer_id}-${o.suggested_category}`}>
      <p><span className="font-semibold">Why: </span>{o.reason}</p>
      <p className="mt-1 font-semibold">Evidence fields</p>
      <ul className="list-disc pl-5">{Object.entries(o.evidence_fields).map(([k, v]) => <li key={k}>{k}: {String(v)}</li>)}</ul>
      <p className="mt-1"><span className="font-semibold">Data confidence: </span>{o.data_confidence} (evidence completeness only, not a purchase probability)</p>
      {o.missing_evidence.length ? <p className="mt-1">Missing evidence: {o.missing_evidence.join(', ')}</p> : null}
      {o.caution ? <p className="mt-2 text-amber-900">Caution: {o.caution}</p> : null}
      <p className="mt-2 font-medium">Human review required. No price, conversion probability or revenue uplift is estimated; nothing is sent to the customer.</p>
    </div>
  );
}

export function OpportunitiesPage() {
  const api = useRevenue();
  const summary = useAsync(() => api.opportunitiesSummary(), [api]);
  const [query, setQuery] = useState<OpportunityQuery>({ page: 1, page_size: 15, eligibility: 'ELIGIBLE' });
  const list = useAsync(() => api.opportunities(query), [api, query]);
  const [open, setOpen] = useState<string | null>(null);

  return (
    <div className="space-y-6">
      <PageIntro title="Upsell & Cross-sell" description="Advisory, rule-based service-gap observations. They are not purchase propensities and require human review before any action." />
      <AsyncView state={summary} label="Loading opportunity summary">
        {(s) => (
          <>
            <div className="grid gap-4 sm:grid-cols-2">{s.metrics.map((m) => <KpiCard key={m.key} metric={m} />)}</div>
            <Notice tone="info">{formatNumber(s.customers_with_opportunity)} customers have at least one eligible observation across {formatNumber(s.eligible_recommendations)} recommendations.</Notice>
            <Panel title="Eligible opportunities by type" badge={<StatusBadge status="PROXY" />}>
              <BarChart title="Eligible opportunities by type" valueLabel="recommendations" data={Object.entries(s.by_type).map(([k, v]) => ({ label: titleCase(k), value: v }))} format={(v) => formatNumber(v)} />
            </Panel>
            <WarningList items={s.warnings} />
          </>
        )}
      </AsyncView>
      <Panel title="Recommendations" subtitle="Select a row to see the reason and evidence.">
        <div className="mb-3 flex flex-wrap gap-3 text-sm">
          <label className="flex items-center gap-2">Type
            <select aria-label="Type filter" className="field w-auto !py-1" value={query.recommendation_type ?? ''}
              onChange={(e) => setQuery({ ...query, recommendation_type: e.target.value || undefined, page: 1 })}>
              <option value="">All</option>{TYPES.map((t) => <option key={t} value={t}>{titleCase(t)}</option>)}
            </select>
          </label>
          <label className="flex items-center gap-2">Eligibility
            <select aria-label="Eligibility filter" className="field w-auto !py-1" value={query.eligibility ?? ''}
              onChange={(e) => setQuery({ ...query, eligibility: e.target.value || undefined, page: 1 })}>
              <option value="">All</option>{ELIGIBILITY.map((t) => <option key={t} value={t}>{titleCase(t)}</option>)}
            </select>
          </label>
        </div>
        <AsyncView state={list} label="Loading recommendations">
          {(p) =>
            p.items.length === 0 ? <EmptyState title="No recommendations match these filters." /> : (
              <>
                <div className="overflow-x-auto">
                  <table className="min-w-full text-left text-sm">
                    <caption className="sr-only">Advisory recommendations</caption>
                    <thead className="border-b border-slate-200 text-xs text-slate-500">
                      <tr>{['Customer', 'Type', 'Suggested category', 'Eligibility', 'Confidence', 'Status', ''].map((h) => <th key={h} scope="col" className="px-3 py-2">{h}</th>)}</tr>
                    </thead>
                    <tbody className="divide-y divide-slate-100">
                      {p.items.map((o) => {
                        const id = `${o.customer_id}|${o.recommendation_type}|${o.suggested_category}`;
                        return (
                          <Fragment key={id}>
                            <tr>
                              <td className="px-3 py-2">{o.customer_id}</td>
                              <td className="px-3 py-2">{titleCase(o.recommendation_type)}</td>
                              <td className="px-3 py-2">{o.suggested_category}</td>
                              <td className="px-3 py-2">{titleCase(o.eligibility)}</td>
                              <td className="px-3 py-2">{o.data_confidence}</td>
                              <td className="px-3 py-2">Pending human review</td>
                              <td className="px-3 py-2">
                                <button type="button" aria-expanded={open === id} onClick={() => setOpen(open === id ? null : id)} className="text-xs font-medium text-brand-700 hover:underline">
                                  {open === id ? 'Hide' : 'Explain'}
                                </button>
                              </td>
                            </tr>
                            {open === id ? <tr><td colSpan={7} className="px-3 pb-3"><Explanation o={o} /></td></tr> : null}
                          </Fragment>
                        );
                      })}
                    </tbody>
                  </table>
                </div>
                <Pagination page={p.page} pageCount={p.page_count} total={p.total} onPage={(n) => setQuery({ ...query, page: n })} />
              </>
            )
          }
        </AsyncView>
      </Panel>
    </div>
  );
}
