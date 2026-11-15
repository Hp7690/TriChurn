import { Bar, BarChart, CartesianGrid, Legend, ResponsiveContainer, Tooltip, XAxis, YAxis } from 'recharts';
import type { CampaignEstimate, RiskBandSummary, ScenarioResult } from '../types/retention';
import { formatCompactMoney, formatMoney } from '../utils/money';
import { ChartFrame } from './ChartFrame';

const MARGIN = { top: 8, right: 8, left: 0, bottom: 0 };

export function BandExposureChart({ data, currency }: { data: RiskBandSummary[]; currency: string }) {
  const description = `Value at risk by risk band: ${data.map((d) => `${d.risk_band} ${formatMoney(d.value_at_risk, currency)}`).join('; ')}.`;
  return (
    <ChartFrame description={description} isEmpty={data.every((d) => d.customers === 0)}>
      <ResponsiveContainer width="100%" height="100%">
        <BarChart data={data} margin={MARGIN}>
          <CartesianGrid strokeDasharray="3 3" vertical={false} />
          <XAxis dataKey="risk_band" />
          <YAxis tickFormatter={(v: number) => formatCompactMoney(v, currency)} width={64} />
          <Tooltip formatter={(value, name) => [formatMoney(Number(value), currency), String(name)]} />
          <Legend />
          <Bar dataKey="total_clv" name="Total CLV" fill="#a5b4fc" radius={[4, 4, 0, 0]} isAnimationActive={false} />
          <Bar dataKey="value_at_risk" name="Value at risk" fill="#e11d48" radius={[4, 4, 0, 0]} isAnimationActive={false} />
        </BarChart>
      </ResponsiveContainer>
    </ChartFrame>
  );
}

export function CampaignEstimateChart({ data, currency }: { data: CampaignEstimate[]; currency: string }) {
  const description = `Estimated cost versus estimated retained revenue per recommended campaign: ${data
    .map((d) => `${d.action_name} cost ${formatMoney(d.estimated_total_cost, currency)}, revenue ${formatMoney(d.estimated_retained_revenue, currency)}`)
    .join('; ')}.`;
  return (
    <ChartFrame description={description} isEmpty={data.length === 0}>
      <ResponsiveContainer width="100%" height="100%">
        <BarChart data={data} margin={MARGIN}>
          <CartesianGrid strokeDasharray="3 3" vertical={false} />
          <XAxis dataKey="action_name" tick={{ fontSize: 11 }} interval={0} />
          <YAxis tickFormatter={(v: number) => formatCompactMoney(v, currency)} width={64} />
          <Tooltip formatter={(value, name) => [formatMoney(Number(value), currency), String(name)]} />
          <Legend />
          <Bar dataKey="estimated_total_cost" name="Estimated cost" fill="#94a3b8" radius={[4, 4, 0, 0]} isAnimationActive={false} />
          <Bar dataKey="estimated_retained_revenue" name="Estimated retained revenue" fill="#5869e8" radius={[4, 4, 0, 0]} isAnimationActive={false} />
        </BarChart>
      </ResponsiveContainer>
    </ChartFrame>
  );
}

export function ScenarioComparisonChart({ data, currency }: { data: ScenarioResult[]; currency: string }) {
  const description = `Scenario comparison (estimates): ${data
    .map((d) => `${d.name} cost ${formatMoney(d.total_cost, currency)}, retained revenue ${formatMoney(d.estimated_retained_revenue, currency)}, net ${formatMoney(d.estimated_net_benefit, currency)}`)
    .join('; ')}.`;
  return (
    <ChartFrame description={description} isEmpty={data.length === 0}>
      <ResponsiveContainer width="100%" height="100%">
        <BarChart data={data} margin={MARGIN}>
          <CartesianGrid strokeDasharray="3 3" vertical={false} />
          <XAxis dataKey="name" tick={{ fontSize: 11 }} interval={0} />
          <YAxis tickFormatter={(v: number) => formatCompactMoney(v, currency)} width={64} />
          <Tooltip formatter={(value, name) => [formatMoney(Number(value), currency), String(name)]} />
          <Legend />
          <Bar dataKey="total_cost" name="Est. cost" fill="#94a3b8" radius={[4, 4, 0, 0]} isAnimationActive={false} />
          <Bar dataKey="estimated_retained_revenue" name="Est. retained revenue" fill="#5869e8" radius={[4, 4, 0, 0]} isAnimationActive={false} />
          <Bar dataKey="estimated_net_benefit" name="Est. net benefit" fill="#059669" radius={[4, 4, 0, 0]} isAnimationActive={false} />
        </BarChart>
      </ResponsiveContainer>
    </ChartFrame>
  );
}
