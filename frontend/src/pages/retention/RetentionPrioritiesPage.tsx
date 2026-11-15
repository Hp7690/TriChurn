import { useMemo, useState } from 'react';
import { Link } from 'react-router-dom';
import { AsyncBoundary } from '../../components/AsyncBoundary';
import { Card } from '../../components/Card';
import { CustomerSearch } from '../../components/CustomerSearch';
import { DecisionBadge } from '../../components/DecisionBadge';
import { LoadingSkeleton } from '../../components/LoadingSkeleton';
import { Pagination } from '../../components/Pagination';
import { TierBadge } from '../../components/retention/badges';
import { useAsync } from '../../hooks/useAsync';
import { useRetention } from '../../services/retention';
import type { Decision, PriorityQuery, PrioritySortField, PriorityTier } from '../../types/retention';
import { formatPercent } from '../../utils/format';
import { formatMoney } from '../../utils/money';

const PAGE_SIZE = 25;
const select = 'field';
const RISK_BANDS = ['LOW', 'MEDIUM', 'HIGH', 'CRITICAL'];
const TIERS: PriorityTier[] = ['P1', 'P2', 'P3', 'P4', 'MONITOR'];
const SORTS: Array<{ value: PrioritySortField; label: string }> = [
  { value: 'rank', label: 'Priority rank' },
  { value: 'priority_score', label: 'Priority score' },
  { value: 'value_at_risk', label: 'Value at risk' },
  { value: 'churn_probability', label: 'Churn probability' },
  { value: 'expected_net_benefit', label: 'Estimated net benefit' },
  { value: 'clv', label: 'CLV' },
];

interface Filters {
  search: string;
  riskBand: string;
  tier: string;
  decision: string;
  sortBy: PrioritySortField;
  descending: boolean;
}

const DEFAULTS: Filters = { search: '', riskBand: '', tier: '', decision: '', sortBy: 'rank', descending: false };

export function RetentionPrioritiesPage() {
  const service = useRetention();
  const [filters, setFilters] = useState<Filters>(DEFAULTS);
  const [page, setPage] = useState(1);

  const query = useMemo<PriorityQuery>(
    () => ({
      page,
      pageSize: PAGE_SIZE,
      search: filters.search.trim() || undefined,
      riskBand: filters.riskBand || undefined,
      tier: (filters.tier || undefined) as PriorityTier | undefined,
      decision: (filters.decision || undefined) as Decision | undefined,
      sortBy: filters.sortBy,
      descending: filters.descending,
    }),
    [filters, page],
  );
  const state = useAsync(() => service.getPriorities(query), [service, query]);

  const update = (patch: Partial<Filters>) => {
    setFilters((f) => ({ ...f, ...patch }));
    setPage(1);
  };

  return (
    <div className="space-y-6">
      <Card>
        <div className="grid gap-3 sm:grid-cols-2 lg:grid-cols-6">
          <div className="lg:col-span-2">
            <CustomerSearch id="priority-search" value={filters.search} onChange={(search) => update({ search })} />
          </div>
          <div>
            <label htmlFor="pf-risk" className="field-label">Risk band</label>
            <select id="pf-risk" className={select} value={filters.riskBand} onChange={(e) => update({ riskBand: e.target.value })}>
              <option value="">All</option>
              {RISK_BANDS.map((b) => <option key={b} value={b}>{b}</option>)}
            </select>
          </div>
          <div>
            <label htmlFor="pf-tier" className="field-label">Priority tier</label>
            <select id="pf-tier" className={select} value={filters.tier} onChange={(e) => update({ tier: e.target.value })}>
              <option value="">All</option>
              {TIERS.map((t) => <option key={t} value={t}>{t}</option>)}
            </select>
          </div>
          <div>
            <label htmlFor="pf-decision" className="field-label">Phase 4 decision</label>
            <select id="pf-decision" className={select} value={filters.decision} onChange={(e) => update({ decision: e.target.value })}>
              <option value="">All</option>
              <option value="INTERVENE">Intervene</option>
              <option value="DO_NOT_INTERVENE">Do not intervene</option>
            </select>
          </div>
          <div>
            <label htmlFor="pf-sort" className="field-label">Sort by</label>
            <div className="flex gap-2">
              <select id="pf-sort" className={select} value={filters.sortBy} onChange={(e) => update({ sortBy: e.target.value as PrioritySortField })}>
                {SORTS.map((s) => <option key={s.value} value={s.value}>{s.label}</option>)}
              </select>
              <button
                type="button"
                onClick={() => update({ descending: !filters.descending })}
                aria-label={`Sort direction: ${filters.descending ? 'descending' : 'ascending'}. Activate to toggle.`}
                className="btn btn-secondary"
              >
                {filters.descending ? '↓' : '↑'}
              </button>
            </div>
          </div>
        </div>
      </Card>

      <AsyncBoundary
        state={state}
        skeleton={<LoadingSkeleton variant="table" rows={8} />}
        isEmpty={(p) => p.total === 0}
        emptyTitle="No customers match these filters"
        emptyDescription="Try a different risk band, tier or search term."
        errorTitle="Unable to load retention priorities."
      >
        {(p) => (
          <Card description={p.score_note}>
            <p className="mb-3 text-sm text-slate-600" aria-live="polite">{p.total.toLocaleString('en-US')} customers</p>
            <div className="overflow-x-auto rounded-lg border border-slate-200">
              <table className="w-full min-w-[980px] text-sm">
                <caption className="sr-only">Retention priorities</caption>
                <thead className="bg-slate-50 text-xs text-slate-600">
                  <tr>
                    <th scope="col" className="px-3 py-2.5 text-left">Rank</th>
                    <th scope="col" className="px-3 py-2.5 text-left">Customer</th>
                    <th scope="col" className="px-3 py-2.5 text-left">Tier</th>
                    <th scope="col" className="px-3 py-2.5 text-right">Score</th>
                    <th scope="col" className="px-3 py-2.5 text-right">Churn prob.</th>
                    <th scope="col" className="px-3 py-2.5 text-right">Value at risk</th>
                    <th scope="col" className="px-3 py-2.5 text-left">Phase 4 action</th>
                    <th scope="col" className="px-3 py-2.5 text-left">Decision</th>
                    <th scope="col" className="px-3 py-2.5 text-left">Why</th>
                  </tr>
                </thead>
                <tbody className="divide-y divide-slate-100 align-top">
                  {p.items.map((item) => (
                    <tr key={item.customer.customer_id}>
                      <td className="px-3 py-2.5 tabular-nums">{item.rank}</td>
                      <td className="px-3 py-2.5">
                        <Link to={`/retention/recommendations/${encodeURIComponent(item.customer.customer_id)}`} className="font-medium text-brand-700 hover:underline">
                          {item.customer.customer_id}
                        </Link>
                      </td>
                      <td className="px-3 py-2.5"><TierBadge tier={item.tier} /></td>
                      <td className="px-3 py-2.5 text-right tabular-nums">{item.score.toFixed(1)}</td>
                      <td className="px-3 py-2.5 text-right tabular-nums">{formatPercent(item.customer.churn_probability)}</td>
                      <td className="px-3 py-2.5 text-right tabular-nums">{formatMoney(item.customer.value_at_risk)}</td>
                      <td className="px-3 py-2.5">{item.customer.decision === 'INTERVENE' ? item.customer.recommended_action : '—'}</td>
                      <td className="px-3 py-2.5"><DecisionBadge decision={item.customer.decision === 'INTERVENE' ? 'Intervene' : 'Do not intervene'} /></td>
                      <td className="px-3 py-2.5">
                        <details>
                          <summary className="cursor-pointer text-brand-700">Reasons</summary>
                          <ul className="mt-1 max-w-sm list-disc space-y-1 pl-4 text-xs text-slate-700">
                            {item.reasons.map((r) => <li key={r}>{r}</li>)}
                          </ul>
                        </details>
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
            <Pagination page={p.page} pageCount={p.page_count} total={p.total} pageSize={p.page_size} onPageChange={setPage} />
          </Card>
        )}
      </AsyncBoundary>
    </div>
  );
}
