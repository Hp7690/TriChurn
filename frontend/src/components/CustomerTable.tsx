import { ArrowDown, ArrowUp, ArrowUpDown } from 'lucide-react';
import { memo } from 'react';
import type { CustomerSortKey, IntelligenceResult, SortDirection } from '../types';
import { cn } from '../utils/cn';
import { formatCurrency, formatPercent } from '../utils/format';
import { RISK_COLORS } from '../utils/theme';
import { DecisionBadge } from './DecisionBadge';
import { RiskBadge } from './RiskBadge';
import { SegmentBadge } from './SegmentBadge';

interface Column {
  key: CustomerSortKey | null;
  label: string;
  align?: 'right';
}

const COLUMNS: Column[] = [
  { key: 'customerId', label: 'Customer ID' },
  { key: 'churnProbability', label: 'Churn Probability' },
  { key: 'riskBand', label: 'Risk Band' },
  { key: 'segment', label: 'Segment' },
  { key: 'clv', label: 'CLV', align: 'right' },
  { key: 'valueAtRisk', label: 'VaR', align: 'right' },
  { key: 'expectedNetBenefit', label: 'ENB', align: 'right' },
  { key: null, label: 'Recommended Action' },
  { key: null, label: 'Decision' },
];

interface CustomerTableProps {
  rows: readonly IntelligenceResult[];
  onSelect: (customerId: string) => void;
  sortKey?: CustomerSortKey;
  sortDirection?: SortDirection;
  /** When provided, sortable column headers become buttons. */
  onSort?: (key: CustomerSortKey) => void;
  caption?: string;
}

function CustomerTableBase({ rows, onSelect, sortKey, sortDirection, onSort, caption = 'Customers' }: CustomerTableProps) {
  return (
    <div className="scrollbar-thin overflow-x-auto rounded-xl border border-slate-200">
      <table className="min-w-[960px] w-full divide-y divide-slate-200 text-sm">
        <caption className="sr-only">{caption}</caption>
        <thead className="bg-sunken">
          <tr>
            {COLUMNS.map((col) => {
              const sortable = col.key !== null && onSort !== undefined;
              const active = col.key !== null && col.key === sortKey;
              return (
                <th
                  key={col.label}
                  scope="col"
                  aria-sort={sortable ? (active ? (sortDirection === 'asc' ? 'ascending' : 'descending') : 'none') : undefined}
                  className={cn(
                    'px-4 py-3 text-xs font-semibold text-slate-500',
                    col.align === 'right' ? 'text-right' : 'text-left',
                  )}
                >
                  {sortable && col.key ? (
                    <button
                      type="button"
                      onClick={() => col.key && onSort?.(col.key)}
                      className="inline-flex items-center gap-1 hover:text-slate-900"
                    >
                      {col.label}
                      {active ? (
                        sortDirection === 'asc' ? (
                          <ArrowUp className="h-3.5 w-3.5" aria-hidden="true" />
                        ) : (
                          <ArrowDown className="h-3.5 w-3.5" aria-hidden="true" />
                        )
                      ) : (
                        <ArrowUpDown className="h-3.5 w-3.5 text-slate-400" aria-hidden="true" />
                      )}
                    </button>
                  ) : (
                    col.label
                  )}
                </th>
              );
            })}
          </tr>
        </thead>
        <tbody className="divide-y divide-slate-100 bg-surface">
          {rows.map((row) => {
            const id = row.prediction.customerId;
            const p = row.prediction.churnProbability;
            return (
              <tr key={id} onClick={() => onSelect(id)} className="cursor-pointer transition-colors hover:bg-sunken">
                <td className="whitespace-nowrap px-4 py-3">
                  <button
                    type="button"
                    onClick={(event) => {
                      event.stopPropagation();
                      onSelect(id);
                    }}
                    className="font-medium text-brand-700 hover:underline"
                  >
                    {id}
                  </button>
                </td>
                <td className="px-4 py-3">
                  <div className="flex items-center gap-2">
                    <span className="w-14 tabular-nums">{formatPercent(p)}</span>
                    <div className="h-1.5 w-16 rounded-full bg-slate-200" aria-hidden="true">
                      <div
                        className="h-full rounded-full"
                        style={{ width: `${Math.round(p * 100)}%`, backgroundColor: RISK_COLORS[row.prediction.riskBand] }}
                      />
                    </div>
                  </div>
                </td>
                <td className="px-4 py-3">
                  <RiskBadge band={row.prediction.riskBand} />
                </td>
                <td className="px-4 py-3">
                  <SegmentBadge segmentId={row.segment.segmentId} label={row.segment.label} />
                </td>
                <td className="px-4 py-3 text-right tabular-nums">{formatCurrency(row.business.clv, row.business.currency)}</td>
                <td className="px-4 py-3 text-right tabular-nums">{formatCurrency(row.business.valueAtRisk, row.business.currency)}</td>
                <td
                  className={cn(
                    'px-4 py-3 text-right tabular-nums',
                    row.business.expectedNetBenefit < 0 ? 'text-rose-700' : 'text-slate-900',
                  )}
                >
                  {formatCurrency(row.business.expectedNetBenefit, row.business.currency)}
                </td>
                <td className="whitespace-nowrap px-4 py-3 text-slate-700">
                  {row.business.bestAction?.name ?? 'No action'}
                </td>
                <td className="px-4 py-3">
                  <DecisionBadge decision={row.business.decision} />
                </td>
              </tr>
            );
          })}
        </tbody>
      </table>
    </div>
  );
}

export const CustomerTable = memo(CustomerTableBase);
