import { Bar, BarChart, CartesianGrid, Legend, ResponsiveContainer, Tooltip, XAxis, YAxis } from 'recharts';
import type { ExposurePoint } from '../types';
import { formatCompactCurrency, formatCurrency } from '../utils/format';
import { ChartFrame } from './ChartFrame';

export function ValueAtRiskChart({
  data,
  currency = 'USD',
}: {
  data: ExposurePoint[];
  currency?: string | null;
}) {
  const description = `CLV and value at risk by churn risk band: ${data
    .map((d) => `${d.band} risk CLV ${formatCurrency(d.totalClv, currency ?? 'USD')}, VaR ${formatCurrency(d.valueAtRisk, currency ?? 'USD')}`)
    .join('; ')}.`;
  return (
    <ChartFrame description={description} isEmpty={data.every((d) => d.customers === 0)}>
      <ResponsiveContainer width="100%" height="100%">
        <BarChart data={data} margin={{ top: 8, right: 8, left: 0, bottom: 0 }}>
          <CartesianGrid strokeDasharray="3 3" vertical={false} />
          <XAxis dataKey="band" tickFormatter={(v: string) => `${v} risk`} />
          <YAxis tickFormatter={(v: number) => formatCompactCurrency(v, currency ?? 'USD')} width={64} />
          <Tooltip formatter={(value, name) => [formatCurrency(Number(value), currency ?? 'USD'), String(name)]} />
          <Legend />
          <Bar dataKey="totalClv" name="Total CLV" fill="#a5b4fc" radius={[4, 4, 0, 0]} isAnimationActive={false} />
          <Bar dataKey="valueAtRisk" name="Value at Risk" fill="#e11d48" radius={[4, 4, 0, 0]} isAnimationActive={false} />
        </BarChart>
      </ResponsiveContainer>
    </ChartFrame>
  );
}
