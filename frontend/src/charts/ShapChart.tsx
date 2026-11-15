import { Bar, BarChart, CartesianGrid, Cell, ReferenceLine, ResponsiveContainer, Tooltip, XAxis, YAxis } from 'recharts';
import type { ShapContribution } from '../types';
import { formatSigned } from '../utils/format';
import { NEGATIVE_SHAP_COLOR, POSITIVE_SHAP_COLOR } from '../utils/theme';
import { ChartFrame } from './ChartFrame';

/**
 * Renders already-computed Phase 3 contributions. The frontend performs no
 * SHAP calculation of its own.
 */
export function ShapChart({ contributions }: { contributions: ShapContribution[] }) {
  const data = contributions.map((c) => ({
    label: `${c.feature} = ${c.featureValue}`,
    contribution: c.contribution,
  }));
  const description = `Feature contributions to churn risk (log-odds): ${contributions
    .map((c) => `${c.feature} ${c.featureValue} ${formatSigned(c.contribution)}`)
    .join('; ')}.`;
  return (
    <ChartFrame description={description} isEmpty={data.length === 0} height={Math.max(240, data.length * 36 + 40)}>
      <ResponsiveContainer width="100%" height="100%">
        <BarChart data={data} layout="vertical" margin={{ top: 4, right: 16, left: 8, bottom: 0 }}>
          <CartesianGrid strokeDasharray="3 3" horizontal={false} />
          <XAxis type="number" tickFormatter={(v: number) => formatSigned(v, 1)} />
          <YAxis type="category" dataKey="label" width={190} tick={{ fontSize: 12 }} interval={0} />
          <Tooltip formatter={(value) => [formatSigned(Number(value)), 'Contribution (log-odds)']} />
          <ReferenceLine x={0} stroke="var(--chart-axis-strong)" />
          <Bar dataKey="contribution" radius={3} isAnimationActive={false}>
            {data.map((d) => (
              <Cell key={d.label} fill={d.contribution >= 0 ? POSITIVE_SHAP_COLOR : NEGATIVE_SHAP_COLOR} />
            ))}
          </Bar>
        </BarChart>
      </ResponsiveContainer>
    </ChartFrame>
  );
}
