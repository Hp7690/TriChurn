import { ArrowDownWideNarrow, ArrowUpNarrowWide } from 'lucide-react';
import type { CustomerSortKey, RiskBand, SegmentId, SortDirection } from '../types';
import { SEGMENT_META, SEGMENT_ORDER } from '../utils/segments';
import { RISK_BANDS } from '../utils/theme';
import { CustomerSearch } from './CustomerSearch';

export interface CustomerFilterState {
  search: string;
  risk: RiskBand | 'all';
  segment: SegmentId | 'all';
  minProbability: number;
  sortBy: CustomerSortKey;
  sortDirection: SortDirection;
}

export const DEFAULT_CUSTOMER_FILTERS: CustomerFilterState = {
  search: '',
  risk: 'all',
  segment: 'all',
  minProbability: 0,
  sortBy: 'churnProbability',
  sortDirection: 'desc',
};

const PROBABILITY_OPTIONS: Array<{ value: number; label: string }> = [
  { value: 0, label: 'Any' },
  { value: 0.3, label: '≥ 30%' },
  { value: 0.5, label: '≥ 50%' },
  { value: 0.7, label: '≥ 70%' },
  { value: 0.85, label: '≥ 85%' },
];

const SORT_OPTIONS: Array<{ value: CustomerSortKey; label: string }> = [
  { value: 'churnProbability', label: 'Churn probability' },
  { value: 'valueAtRisk', label: 'Value at risk' },
  { value: 'expectedNetBenefit', label: 'Expected net benefit' },
  { value: 'clv', label: 'CLV' },
  { value: 'riskBand', label: 'Risk band' },
  { value: 'segment', label: 'Segment' },
  { value: 'customerId', label: 'Customer ID' },
];

const selectClass = 'field';

interface CustomerFiltersProps {
  value: CustomerFilterState;
  onChange: (patch: Partial<CustomerFilterState>) => void;
}

export function CustomerFilters({ value, onChange }: CustomerFiltersProps) {
  const descending = value.sortDirection === 'desc';
  return (
    <div className="grid gap-3 sm:grid-cols-2 lg:grid-cols-6">
      <div className="lg:col-span-2">
        <CustomerSearch value={value.search} onChange={(search) => onChange({ search })} />
      </div>
      <div>
        <label htmlFor="filter-risk" className="field-label">
          Risk band
        </label>
        <select
          id="filter-risk"
          className={selectClass}
          value={value.risk}
          onChange={(e) => onChange({ risk: e.target.value as RiskBand | 'all' })}
        >
          <option value="all">All</option>
          {RISK_BANDS.map((band) => (
            <option key={band} value={band}>
              {band}
            </option>
          ))}
        </select>
      </div>
      <div>
        <label htmlFor="filter-segment" className="field-label">
          Segment
        </label>
        <select
          id="filter-segment"
          className={selectClass}
          value={value.segment}
          onChange={(e) => onChange({ segment: e.target.value as SegmentId | 'all' })}
        >
          <option value="all">All segments</option>
          {SEGMENT_ORDER.map((id) => (
            <option key={id} value={id}>
              {SEGMENT_META[id].label}
            </option>
          ))}
        </select>
      </div>
      <div>
        <label htmlFor="filter-probability" className="field-label">
          Churn probability
        </label>
        <select
          id="filter-probability"
          className={selectClass}
          value={String(value.minProbability)}
          onChange={(e) => onChange({ minProbability: Number(e.target.value) })}
        >
          {PROBABILITY_OPTIONS.map((o) => (
            <option key={o.value} value={String(o.value)}>
              {o.label}
            </option>
          ))}
        </select>
      </div>
      <div>
        <label htmlFor="filter-sort" className="field-label">
          Sort by
        </label>
        <div className="flex gap-2">
          <select
            id="filter-sort"
            className={selectClass}
            value={value.sortBy}
            onChange={(e) => onChange({ sortBy: e.target.value as CustomerSortKey })}
          >
            {SORT_OPTIONS.map((o) => (
              <option key={o.value} value={o.value}>
                {o.label}
              </option>
            ))}
          </select>
          <button
            type="button"
            onClick={() => onChange({ sortDirection: descending ? 'asc' : 'desc' })}
            aria-label={`Toggle sort direction (currently ${descending ? 'descending' : 'ascending'})`}
            className="btn btn-secondary px-2.5"
          >
            {descending ? (
              <ArrowDownWideNarrow className="h-4 w-4" aria-hidden="true" />
            ) : (
              <ArrowUpNarrowWide className="h-4 w-4" aria-hidden="true" />
            )}
          </button>
        </div>
      </div>
    </div>
  );
}
