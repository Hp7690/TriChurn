import { Bar, BarChart, CartesianGrid, Cell, ResponsiveContainer, Tooltip, XAxis, YAxis } from 'recharts';
import type { RiskDistributionPoint } from '../types';
import { formatNumber } from '../utils/format';
import { RISK_COLORS } from '../utils/theme';
import { ChartFrame } from './ChartFrame';

export function RiskDistributionChart({ data }: { data: RiskDistributionPoint[] }) {
  const description = `Churn risk distribution: ${data.map((d) => `${d.band} risk ${d.count} customers (${d.percentage}%)`).join('; ')}.`;
  return (
    <ChartFrame description={description} isEmpty={data.every((d) => d.count === 0)}>
      <ResponsiveContainer width="100%" height="100%">
        <BarChart data={data} margin={{ top: 8, right: 8, left: -8, bottom: 0 }}>
          <CartesianGrid strokeDasharray="3 3" vertical={false} />
          <XAxis dataKey="band" tickFormatter={(v: string) => `${v} risk`} />
          <YAxis allowDecimals={false} />
          <Tooltip formatter={(value) => [formatNumber(Number(value)), 'Customers']} />
          <Bar dataKey="count" radius={[6, 6, 0, 0]} isAnimationActive={false}>
            {data.map((d) => (
              <Cell key={d.band} fill={RISK_COLORS[d.band]} />
            ))}
          </Bar>
        </BarChart>
      </ResponsiveContainer>
    </ChartFrame>
  );
}
