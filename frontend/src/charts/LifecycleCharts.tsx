import { Bar, BarChart, CartesianGrid, Legend, ResponsiveContainer, Tooltip, XAxis, YAxis } from 'recharts';
import type { LifecycleGroup } from '../types/experience';
import { formatNumber } from '../utils/format';
import { ChartFrame } from './ChartFrame';

const CONTRACT_COLORS = ['#5869e8', '#0ea5e9', '#10b981', '#f59e0b', '#94a3b8'];

type CountPoint = Pick<LifecycleGroup, 'name' | 'customers'>;

/** Customers per tenure group. */
export function LifecycleCustomersChart({ groups }: { groups: CountPoint[] }) {
  const description = `Customers per tenure lifecycle group: ${groups.map((g) => `${g.name} ${g.customers}`).join('; ')}.`;
  return (
    <ChartFrame description={description} isEmpty={groups.every((g) => g.customers === 0)}>
      <ResponsiveContainer width="100%" height="100%">
        <BarChart data={groups} margin={{ top: 8, right: 8, left: 0, bottom: 0 }}>
          <CartesianGrid strokeDasharray="3 3" vertical={false} />
          <XAxis dataKey="name" tick={{ fontSize: 11 }} interval={0} />
          <YAxis width={56} tickFormatter={(v: number) => formatNumber(v)} />
          <Tooltip formatter={(value) => [formatNumber(Number(value)), 'Customers']} />
          <Bar dataKey="customers" fill="#5869e8" radius={[6, 6, 0, 0]} isAnimationActive={false} />
        </BarChart>
      </ResponsiveContainer>
    </ChartFrame>
  );
}

/** Observed churn rate (actual labels). Groups whose rate is withheld are left out and explained in the table. */
export function LifecycleChurnChart({ groups }: { groups: LifecycleGroup[] }) {
  const data = groups
    .filter((g) => g.churn?.churn_rate_pct != null)
    .map((g) => ({ name: g.name, rate: g.churn?.churn_rate_pct as number }));
  const description = `Observed churn rate by tenure group: ${data.map((d) => `${d.name} ${d.rate}%`).join('; ')}.`;
  return (
    <ChartFrame description={description} isEmpty={data.length === 0}>
      <ResponsiveContainer width="100%" height="100%">
        <BarChart data={data} margin={{ top: 8, right: 8, left: 0, bottom: 0 }}>
          <CartesianGrid strokeDasharray="3 3" vertical={false} />
          <XAxis dataKey="name" tick={{ fontSize: 11 }} interval={0} />
          <YAxis width={48} unit="%" domain={[0, 100]} />
          <Tooltip formatter={(value) => [`${Number(value).toFixed(2)}%`, 'Observed churn rate']} />
          <Bar dataKey="rate" fill="#e11d48" radius={[6, 6, 0, 0]} isAnimationActive={false} />
        </BarChart>
      </ResponsiveContainer>
    </ChartFrame>
  );
}

/** Contract mix per group (counts). */
export function LifecycleContractChart({ groups }: { groups: LifecycleGroup[] }) {
  const contracts = Array.from(new Set(groups.flatMap((g) => Object.keys(g.contract_distribution ?? {})))).sort();
  const data = groups.map((g) => ({ name: g.name, ...(g.contract_distribution ?? {}) }));
  const description = `Contract types per tenure group: ${contracts.join(', ')}.`;
  return (
    <ChartFrame description={description} isEmpty={contracts.length === 0} height={280}>
      <ResponsiveContainer width="100%" height="100%">
        <BarChart data={data} margin={{ top: 8, right: 8, left: 0, bottom: 0 }}>
          <CartesianGrid strokeDasharray="3 3" vertical={false} />
          <XAxis dataKey="name" tick={{ fontSize: 11 }} interval={0} />
          <YAxis width={56} tickFormatter={(v: number) => formatNumber(v)} />
          <Tooltip />
          <Legend verticalAlign="bottom" />
          {contracts.map((c, i) => (
            <Bar key={c} dataKey={c} stackId="contract" fill={CONTRACT_COLORS[i % CONTRACT_COLORS.length]} isAnimationActive={false} />
          ))}
        </BarChart>
      </ResponsiveContainer>
    </ChartFrame>
  );
}
