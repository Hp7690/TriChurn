import { Link } from 'react-router-dom';
import type { IntelligenceResult } from '../types';
import { RiskBadge } from './RiskBadge';

interface CustomerRankListProps {
  items: readonly IntelligenceResult[];
  metricLabel: string;
  metric: (item: IntelligenceResult) => string;
}

export function CustomerRankList({ items, metricLabel, metric }: CustomerRankListProps) {
  if (items.length === 0) return <p className="text-sm text-slate-600">No customers match this view.</p>;
  return (
    <ol className="divide-y divide-slate-100">
      {items.map((item, index) => (
        <li key={item.prediction.customerId} className="flex items-center justify-between gap-3 py-2.5">
          <div className="flex min-w-0 items-center gap-3">
            <span className="w-5 text-xs font-medium text-slate-500">{index + 1}</span>
            <Link to={`/customers/${encodeURIComponent(item.prediction.customerId)}`} className="font-medium text-brand-700 hover:underline">
              {item.prediction.customerId}
            </Link>
            <RiskBadge band={item.prediction.riskBand} />
          </div>
          <div className="text-right">
            <p className="text-sm font-semibold tabular-nums text-slate-900">{metric(item)}</p>
            <p className="text-xs text-slate-500">{metricLabel}</p>
          </div>
        </li>
      ))}
    </ol>
  );
}
