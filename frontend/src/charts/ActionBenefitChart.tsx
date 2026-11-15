import { Bar, BarChart, CartesianGrid, ResponsiveContainer, Tooltip, XAxis, YAxis } from 'recharts';
import type { ActionSummary } from '../types';
import { formatCompactCurrency, formatCurrency } from '../utils/format';
import { ChartFrame } from './ChartFrame';

export function ActionBenefitChart({
  data,
  currency = 'USD',
}: {
  data: ActionSummary[];
  currency?: string | null;
}) {
  const rows = data.filter((d) => d.customers > 0);
  const description = `Expected benefit by recommended action: ${rows
    .map((d) => `${d.action} ${formatCurrency(d.expectedBenefit, currency ?? 'USD')} across ${d.customers} customers`)
    .join('; ')}.`;
  return (
    <ChartFrame description={description} isEmpty={rows.length === 0} height={Math.max(200, rows.length * 56 + 40)}>
      <ResponsiveContainer width="100%" height="100%">
        <BarChart data={rows} layout="vertical" margin={{ top: 4, right: 16, left: 8, bottom: 0 }}>
          <CartesianGrid strokeDasharray="3 3" horizontal={false} />
          <XAxis type="number" tickFormatter={(v: number) => formatCompactCurrency(v, currency ?? 'USD')} />
          <YAxis type="category" dataKey="action" width={150} tick={{ fontSize: 12 }} />
          <Tooltip formatter={(value) => [formatCurrency(Number(value), currency ?? 'USD'), 'Expected benefit']} />
          <Bar dataKey="expectedBenefit" fill="#5869e8" radius={[0, 6, 6, 0]} isAnimationActive={false} />
        </BarChart>
      </ResponsiveContainer>
    </ChartFrame>
  );
}
