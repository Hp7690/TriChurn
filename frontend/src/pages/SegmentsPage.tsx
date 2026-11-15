import { useState } from 'react';
import { Link, useNavigate } from 'react-router-dom';
import { SegmentChart, SegmentMetricChart } from '../charts/SegmentChart';
import { AsyncBoundary } from '../components/AsyncBoundary';
import { Card } from '../components/Card';
import { CustomerTable } from '../components/CustomerTable';
import { LoadingSkeleton } from '../components/LoadingSkeleton';
import { PageHeader } from '../components/PageHeader';
import { SegmentBadge } from '../components/SegmentBadge';
import { useAsync } from '../hooks/useAsync';
import { useService } from '../services/ServiceContext';
import type { SegmentId } from '../types';
import { cn } from '../utils/cn';
import { formatCurrency, formatNumber, formatPercent } from '../utils/format';
import { SEGMENT_COLORS } from '../utils/theme';

export function SegmentsPage() {
  const service = useService();
  const navigate = useNavigate();
  const [selected, setSelected] = useState<SegmentId | null>(null);

  const overview = useAsync(() => service.getSegments(), [service]);
  const members = useAsync(
    () =>
      selected
        ? service.listCustomers({ segment: selected, sortBy: 'valueAtRisk', sortDirection: 'desc', pageSize: 10 })
        : Promise.resolve(null),
    [service, selected],
  );

  return (
    <>
      <PageHeader
        title="Customer Segments"
        description="The three segments come from the locked Phase 5 segmentation artifact (K = 3). This page only displays them."
      />
      <AsyncBoundary state={overview} isEmpty={(o) => o.totalCustomers === 0} emptyTitle="No segment data available">
        {(o) => (
          <div className="space-y-6">
            <div className="grid gap-4 md:grid-cols-3">
              {o.segments.map((s) => (
                <button
                  key={s.segmentId}
                  type="button"
                  aria-pressed={selected === s.segmentId}
                  onClick={() => setSelected(selected === s.segmentId ? null : s.segmentId)}
                  className={cn(
                    'rounded-xl border bg-surface p-5 text-left shadow-sm transition hover:shadow-md',
                    selected === s.segmentId ? 'border-brand-500 ring-2 ring-brand-500/40' : 'border-slate-200',
                  )}
                >
                  <div className="flex items-center gap-2">
                    <span className="h-3 w-3 rounded-full" style={{ backgroundColor: SEGMENT_COLORS[s.segmentId] }} aria-hidden="true" />
                    <h2 className="text-base font-semibold text-slate-900">{s.label}</h2>
                  </div>
                  <p className="mt-1 text-xs text-slate-600">{s.description}</p>
                  <dl className="mt-4 grid grid-cols-2 gap-x-4 gap-y-2 text-sm">
                    <div><dt className="text-xs text-slate-500">Customers</dt><dd className="font-semibold tabular-nums">{formatNumber(s.customerCount)} ({s.percentage}%)</dd></div>
                    <div><dt className="text-xs text-slate-500">Avg churn prob.</dt><dd className="font-semibold tabular-nums">{formatPercent(s.avgChurnProbability)}</dd></div>
                    <div><dt className="text-xs text-slate-500">Total VaR</dt><dd className="font-semibold tabular-nums">{formatCurrency(s.totalVar, o.currency ?? 'USD')}</dd></div>
                    <div><dt className="text-xs text-slate-500">Avg ENB</dt><dd className="font-semibold tabular-nums">{formatCurrency(s.avgEnb, o.currency ?? 'USD')}</dd></div>
                    <div><dt className="text-xs text-slate-500">Intervention rate</dt><dd className="font-semibold tabular-nums">{formatPercent(s.interventionRate, 0)}</dd></div>
                    <div><dt className="text-xs text-slate-500">Recommended action</dt><dd className="font-semibold">{s.recommendedAction}</dd></div>
                  </dl>
                </button>
              ))}
            </div>

            <div className="grid gap-6 lg:grid-cols-2">
              <Card title="Segment Mix" description="Customers per segment">
                <SegmentChart data={o.segments} />
              </Card>
              <Card title="Value at Risk by Segment" description="Total VaR per segment">
                <SegmentMetricChart data={o.segments} metric="totalVar" metricLabel="Total VaR" format={(value) => formatCurrency(value, o.currency ?? 'USD')} />
              </Card>
            </div>

            <Card title="Segment Comparison">
              <div className="overflow-x-auto rounded-lg border border-slate-200">
                <table className="w-full min-w-[820px] text-sm">
                  <caption className="sr-only">Segment comparison</caption>
                  <thead className="bg-slate-50 text-xs text-slate-600">
                    <tr>
                      <th scope="col" className="px-3 py-2.5 text-left">Segment</th>
                      <th scope="col" className="px-3 py-2.5 text-right">Customers</th>
                      <th scope="col" className="px-3 py-2.5 text-right">Share</th>
                      <th scope="col" className="px-3 py-2.5 text-right">Avg churn prob.</th>
                      <th scope="col" className="px-3 py-2.5 text-right">Total VaR</th>
                      <th scope="col" className="px-3 py-2.5 text-right">Avg ENB</th>
                      <th scope="col" className="px-3 py-2.5 text-right">Intervention rate</th>
                      <th scope="col" className="px-3 py-2.5 text-left">Recommended action</th>
                    </tr>
                  </thead>
                  <tbody className="divide-y divide-slate-100">
                    {o.segments.map((s) => (
                      <tr key={s.segmentId} className="hover:bg-slate-50">
                        <td className="px-3 py-2.5">
                          <button type="button" onClick={() => setSelected(s.segmentId)} className="hover:underline">
                            <SegmentBadge segmentId={s.segmentId} label={s.label} />
                          </button>
                        </td>
                        <td className="px-3 py-2.5 text-right tabular-nums">{formatNumber(s.customerCount)}</td>
                        <td className="px-3 py-2.5 text-right tabular-nums">{s.percentage}%</td>
                        <td className="px-3 py-2.5 text-right tabular-nums">{formatPercent(s.avgChurnProbability)}</td>
                        <td className="px-3 py-2.5 text-right tabular-nums">{formatCurrency(s.totalVar, o.currency ?? 'USD')}</td>
                        <td className="px-3 py-2.5 text-right tabular-nums">{formatCurrency(s.avgEnb, o.currency ?? 'USD')}</td>
                        <td className="px-3 py-2.5 text-right tabular-nums">{formatPercent(s.interventionRate, 0)}</td>
                        <td className="px-3 py-2.5">{s.recommendedAction}</td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            </Card>

            <Card
              title={selected ? `Customers in ${o.segments.find((s) => s.segmentId === selected)?.label ?? 'segment'}` : 'Segment customers'}
              description={selected ? 'Top 10 by value at risk' : undefined}
              actions={
                selected ? (
                  <Link to={`/customers?segment=${selected}`} className="text-sm font-medium text-brand-700 hover:underline">
                    View all in Customers →
                  </Link>
                ) : undefined
              }
            >
              {!selected ? (
                <p className="text-sm text-slate-600">Select a segment above to see its customers.</p>
              ) : (
                <AsyncBoundary state={members} skeleton={<LoadingSkeleton variant="table" />} isEmpty={(p) => p === null || p.total === 0} emptyTitle="No customers in this segment">
                  {(page) =>
                    page && (
                      <CustomerTable
                        rows={page.items}
                        caption="Customers in selected segment"
                        onSelect={(id) => navigate(`/customers/${encodeURIComponent(id)}`)}
                      />
                    )
                  }
                </AsyncBoundary>
              )}
            </Card>
          </div>
        )}
      </AsyncBoundary>
    </>
  );
}
