import { useCallback, useMemo, useState } from 'react';
import { useNavigate, useSearchParams } from 'react-router-dom';
import { AsyncBoundary } from '../components/AsyncBoundary';
import { Card } from '../components/Card';
import { CustomerFilters, DEFAULT_CUSTOMER_FILTERS, type CustomerFilterState } from '../components/CustomerFilters';
import { CustomerTable } from '../components/CustomerTable';
import { LoadingSkeleton } from '../components/LoadingSkeleton';
import { PageHeader } from '../components/PageHeader';
import { Pagination } from '../components/Pagination';
import { useAsync } from '../hooks/useAsync';
import { useService } from '../services/ServiceContext';
import type { CustomerQuery, CustomerSortKey, RiskBand } from '../types';
import { isSegmentId } from '../utils/segments';
import { RISK_BANDS } from '../utils/theme';

const PAGE_SIZE = 10;

export function CustomersPage() {
  const service = useService();
  const navigate = useNavigate();
  const [params] = useSearchParams();

  const [filters, setFilters] = useState<CustomerFilterState>(() => {
    const risk = params.get('risk');
    const segment = params.get('segment');
    return {
      ...DEFAULT_CUSTOMER_FILTERS,
      search: params.get('q') ?? '',
      risk: RISK_BANDS.includes(risk as RiskBand) ? (risk as RiskBand) : 'all',
      segment: isSegmentId(segment) ? segment : 'all',
    };
  });
  const [page, setPage] = useState(1);

  const update = useCallback((patch: Partial<CustomerFilterState>) => {
    setFilters((prev) => ({ ...prev, ...patch }));
    setPage(1);
  }, []);

  const toggleSort = useCallback((key: CustomerSortKey) => {
    setFilters((prev) => ({
      ...prev,
      sortBy: key,
      sortDirection: prev.sortBy === key && prev.sortDirection === 'desc' ? 'asc' : 'desc',
    }));
    setPage(1);
  }, []);

  const query = useMemo<CustomerQuery>(() => ({ ...filters, page, pageSize: PAGE_SIZE }), [filters, page]);
  const state = useAsync(() => service.listCustomers(query), [service, query]);

  const reset = () => {
    setFilters(DEFAULT_CUSTOMER_FILTERS);
    setPage(1);
  };

  return (
    <>
      <PageHeader title="Customer Intelligence" description="Search, filter and sort scored customers. Select a customer to see the full explanation." />
      <Card className="mb-6">
        <CustomerFilters value={filters} onChange={update} />
      </Card>
      <AsyncBoundary
        state={state.status === 'loading' ? { ...state, data: null } : state}
        skeleton={<LoadingSkeleton variant="table" rows={8} />}
        isEmpty={(p) => p.total === 0}
        emptyTitle="No customers match these filters"
        emptyDescription="Try widening the risk band, segment or probability filter."
      >
        {(result) => (
          <Card>
            <p className="mb-3 text-sm text-slate-600" aria-live="polite">
              {result.total} customer{result.total === 1 ? '' : 's'} found
            </p>
            <CustomerTable
              rows={result.items}
              sortKey={filters.sortBy}
              sortDirection={filters.sortDirection}
              onSort={toggleSort}
              onSelect={(id) => navigate(`/customers/${encodeURIComponent(id)}`)}
            />
            <Pagination
              page={result.page}
              pageCount={result.pageCount}
              total={result.total}
              pageSize={result.pageSize}
              onPageChange={setPage}
            />
          </Card>
        )}
      </AsyncBoundary>
      {state.status === 'success' && state.data?.total === 0 && (
        <div className="mt-4 text-center">
          <button type="button" onClick={reset} className="text-sm font-medium text-brand-700 hover:underline">
            Reset filters
          </button>
        </div>
      )}
    </>
  );
}
