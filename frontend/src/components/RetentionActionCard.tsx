import { formatCurrency, formatPercent } from '../utils/format';

interface RetentionActionCardProps {
  name: string;
  description?: string;
  cost: number;
  successRate: number;
  customers?: number;
  expectedBenefit?: number;
  currency?: string;
}

export function RetentionActionCard({ name, description, cost, successRate, customers, expectedBenefit, currency = 'USD' }: RetentionActionCardProps) {
  return (
    <article className="rounded-xl border border-slate-200 bg-sunken p-4">
      <h3 className="text-sm font-semibold text-slate-900">{name}</h3>
      {description && <p className="mt-1 text-xs text-slate-600">{description}</p>}
      <dl className="mt-3 grid grid-cols-2 gap-x-4 gap-y-2 text-sm">
        <div>
          <dt className="text-xs text-slate-500">Avg cost</dt>
          <dd className="font-medium tabular-nums">{formatCurrency(cost, currency)}</dd>
        </div>
        <div>
          <dt className="text-xs text-slate-500">Success rate</dt>
          <dd className="font-medium tabular-nums">{formatPercent(successRate, 0)}</dd>
        </div>
        {customers !== undefined && (
          <div>
            <dt className="text-xs text-slate-500">Customers</dt>
            <dd className="font-medium tabular-nums">{customers}</dd>
          </div>
        )}
        {expectedBenefit !== undefined && (
          <div>
            <dt className="text-xs text-slate-500">Expected benefit</dt>
            <dd className="font-medium tabular-nums text-emerald-700">{formatCurrency(expectedBenefit, currency)}</dd>
          </div>
        )}
      </dl>
    </article>
  );
}
