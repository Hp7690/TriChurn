import { Bar, BarChart, CartesianGrid, Cell, Legend, Pie, PieChart, ResponsiveContainer, Tooltip, XAxis, YAxis } from 'recharts';
import type { SegmentProfile } from '../types';
import { formatNumber } from '../utils/format';
import { SEGMENT_COLORS } from '../utils/theme';
import { ChartFrame } from './ChartFrame';

/** Donut: customers per Phase 5 segment. */
export function SegmentChart({ data }: { data: SegmentProfile[] }) {
  const description = `Customer segment distribution: ${data
    .map((d) => `${d.label} ${d.customerCount} customers (${d.percentage}%)`)
    .join('; ')}.`;
  return (
    <ChartFrame description={description} isEmpty={data.every((d) => d.customerCount === 0)}>
      <ResponsiveContainer width="100%" height="100%">
        <PieChart>
          <Pie
            data={data}
            dataKey="customerCount"
            nameKey="label"
            innerRadius="55%"
            outerRadius="80%"
            paddingAngle={2}
            isAnimationActive={false}
          >
            {data.map((d) => (
              <Cell key={d.segmentId} fill={SEGMENT_COLORS[d.segmentId]} />
            ))}
          </Pie>
          <Tooltip formatter={(value) => [formatNumber(Number(value)), 'Customers']} />
          <Legend verticalAlign="bottom" />
        </PieChart>
      </ResponsiveContainer>
    </ChartFrame>
  );
}

interface SegmentMetricChartProps {
  data: SegmentProfile[];
  metric: 'totalVar' | 'avgChurnProbability' | 'avgEnb' | 'customerCount';
  metricLabel: string;
  format: (value: number) => string;
}

/** Bar: one metric compared across the three segments. */
export function SegmentMetricChart({ data, metric, metricLabel, format }: SegmentMetricChartProps) {
  const description = `${metricLabel} by segment: ${data.map((d) => `${d.label} ${format(d[metric])}`).join('; ')}.`;
  return (
    <ChartFrame description={description} isEmpty={data.length === 0}>
      <ResponsiveContainer width="100%" height="100%">
        <BarChart data={data} margin={{ top: 8, right: 8, left: 0, bottom: 0 }}>
          <CartesianGrid strokeDasharray="3 3" vertical={false} />
          <XAxis dataKey="label" tick={{ fontSize: 11 }} interval={0} />
          <YAxis tickFormatter={(v: number) => format(v)} width={64} />
          <Tooltip formatter={(value) => [format(Number(value)), metricLabel]} />
          <Bar dataKey={metric} radius={[6, 6, 0, 0]} isAnimationActive={false}>
            {data.map((d) => (
              <Cell key={d.segmentId} fill={SEGMENT_COLORS[d.segmentId]} />
            ))}
          </Bar>
        </BarChart>
      </ResponsiveContainer>
    </ChartFrame>
  );
}
