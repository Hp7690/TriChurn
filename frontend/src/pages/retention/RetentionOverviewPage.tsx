import { AlertTriangle, Megaphone, Target, TrendingUp, Users, Wallet } from 'lucide-react';
import { Link } from 'react-router-dom';
import { BandExposureChart, CampaignEstimateChart } from '../../charts/RetentionCharts';
import { AsyncBoundary } from '../../components/AsyncBoundary';
import { Card } from '../../components/Card';
import { KpiCard } from '../../components/KpiCard';
import { EstimateBadge, TierBadge } from '../../components/retention/badges';
import { useAsync } from '../../hooks/useAsync';
import { useRetention } from '../../services/retention';
import { formatNumber, formatPercent } from '../../utils/format';
import { formatMoney, formatRatio } from '../../utils/money';

export function RetentionOverviewPage() {
  const service = useRetention();
  const state = useAsync(() => service.getSummary(), [service]);

  return (
    <AsyncBoundary
      state={state}
      isEmpty={(s) => s.total_customers === 0}
      emptyTitle="No scored customers"
      emptyDescription="The retention portfolio is empty, so there is nothing to summarise yet."
      errorTitle="Unable to load the retention summary."
    >
      {(s) => {
        const money = (v: number) => formatMoney(v, s.currency_code);
        return (
          <div className="space-y-6">
            <div className="grid gap-4 sm:grid-cols-2 xl:grid-cols-3">
              <KpiCard label="Revenue at Risk" value={money(s.revenue_at_risk)} hint={`${formatNumber(s.total_customers)} customers scored`} icon={Wallet} tone="danger" />
              <KpiCard label="Intervention Candidates" value={formatNumber(s.intervention_candidates)} hint="Phase 4 decision: intervene" icon={Users} tone="brand" />
              <KpiCard label="High-Priority Customers" value={formatNumber(s.high_priority_customers)} hint={`${money(s.high_priority_value_at_risk)} value at risk (tiers P1–P2)`} icon={AlertTriangle} tone="danger" />
              <KpiCard label="Estimated Campaign Cost" value={money(s.estimated_total_cost)} hint="Estimate · if every recommendation is applied" icon={Megaphone} />
              <KpiCard label="Estimated Retained Revenue" value={money(s.estimated_retained_revenue)} hint="Estimate · under assumed success rates" icon={Target} tone="success" />
              <KpiCard label="Estimated Net Benefit" value={money(s.estimated_net_benefit)} hint={`Estimated ROI ${formatRatio(s.estimated_roi)}`} icon={TrendingUp} tone="success" />
            </div>

            <div className="grid gap-6 lg:grid-cols-2">
              <Card title="Value at Risk by Risk Band" description="Phase 4 value at risk = CLV × churn probability">
                <BandExposureChart data={s.by_risk_band} currency={s.currency_code} />
              </Card>
              <Card title="Recommended Campaigns" description="Estimated cost versus estimated retained revenue" actions={<EstimateBadge />}>
                <CampaignEstimateChart data={s.recommended_campaigns} currency={s.currency_code} />
              </Card>
            </div>

            <Card title="Recommended Campaign Summary" actions={<EstimateBadge />}>
              {s.recommended_campaigns.length === 0 ? (
                <p className="text-sm text-slate-600">The Phase 4 engine recommends no interventions.</p>
              ) : (
                <div className="overflow-x-auto rounded-lg border border-slate-200">
                  <table className="w-full min-w-[760px] text-sm">
                    <caption className="sr-only">Recommended campaigns (estimates)</caption>
                    <thead className="bg-slate-50 text-xs text-slate-600">
                      <tr>
                        {['Action', 'Customers', 'Cost / customer', 'Assumed success', 'Est. cost', 'Est. retained revenue', 'Est. net benefit', 'Est. ROI'].map((h, i) => (
                          <th key={h} scope="col" className={i === 0 ? 'px-3 py-2.5 text-left' : 'px-3 py-2.5 text-right'}>{h}</th>
                        ))}
                      </tr>
                    </thead>
                    <tbody className="divide-y divide-slate-100">
                      {s.recommended_campaigns.map((c) => (
                        <tr key={c.action_id}>
                          <td className="px-3 py-2.5 font-medium">{c.action_name}</td>
                          <td className="px-3 py-2.5 text-right tabular-nums">{formatNumber(c.customers)}</td>
                          <td className="px-3 py-2.5 text-right tabular-nums">{money(c.cost_per_customer)}</td>
                          <td className="px-3 py-2.5 text-right tabular-nums">{formatPercent(c.assumed_success_rate, 0)}</td>
                          <td className="px-3 py-2.5 text-right tabular-nums">{money(c.estimated_total_cost)}</td>
                          <td className="px-3 py-2.5 text-right tabular-nums">{money(c.estimated_retained_revenue)}</td>
                          <td className="px-3 py-2.5 text-right tabular-nums">{money(c.estimated_net_benefit)}</td>
                          <td className="px-3 py-2.5 text-right tabular-nums">{formatRatio(c.estimated_roi)}</td>
                        </tr>
                      ))}
                    </tbody>
                  </table>
                </div>
              )}
            </Card>

            <Card title="Segments" description="Descriptive Phase 5 segments">
              <div className="overflow-x-auto rounded-lg border border-slate-200">
                <table className="w-full min-w-[620px] text-sm">
                  <caption className="sr-only">Segment summary</caption>
                  <thead className="bg-slate-50 text-xs text-slate-600">
                    <tr>
                      <th scope="col" className="px-3 py-2.5 text-left">Segment</th>
                      <th scope="col" className="px-3 py-2.5 text-right">Customers</th>
                      <th scope="col" className="px-3 py-2.5 text-right">Candidates</th>
                      <th scope="col" className="px-3 py-2.5 text-right">Avg churn prob.</th>
                      <th scope="col" className="px-3 py-2.5 text-right">Value at risk</th>
                    </tr>
                  </thead>
                  <tbody className="divide-y divide-slate-100">
                    {s.by_segment.map((g) => (
                      <tr key={g.segment_id}>
                        <td className="px-3 py-2.5 font-medium">{g.segment_name}</td>
                        <td className="px-3 py-2.5 text-right tabular-nums">{formatNumber(g.customers)}</td>
                        <td className="px-3 py-2.5 text-right tabular-nums">{formatNumber(g.intervention_candidates)}</td>
                        <td className="px-3 py-2.5 text-right tabular-nums">{formatPercent(g.average_churn_probability)}</td>
                        <td className="px-3 py-2.5 text-right tabular-nums">{money(g.value_at_risk)}</td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            </Card>

            <Card
              title="Top Retention Priorities"
              description={s.score_note}
              actions={<Link to="/retention/priorities" className="text-sm font-medium text-brand-700 hover:underline">View all priorities →</Link>}
            >
              <ol className="divide-y divide-slate-100">
                {s.top_priorities.map((p) => (
                  <li key={p.customer.customer_id} className="flex flex-wrap items-center justify-between gap-3 py-2.5">
                    <div className="flex items-center gap-3">
                      <span className="w-6 text-xs font-medium text-slate-500">{p.rank}</span>
                      <Link to={`/retention/recommendations/${encodeURIComponent(p.customer.customer_id)}`} className="font-medium text-brand-700 hover:underline">
                        {p.customer.customer_id}
                      </Link>
                      <TierBadge tier={p.tier} />
                      <span className="text-sm text-slate-600">{p.customer.recommended_action}</span>
                    </div>
                    <div className="text-right text-sm tabular-nums">
                      <span className="font-semibold">{money(p.customer.value_at_risk)}</span>
                      <span className="ml-2 text-xs text-slate-500">VaR · score {p.score.toFixed(1)}</span>
                    </div>
                  </li>
                ))}
              </ol>
            </Card>

            <p className="text-xs text-slate-500">
              Model v{s.model_version} · segmentation v{s.segmentation_version} · dataset {s.dataset_sha256.slice(0, 12)} · scored {s.scored_at}. {s.note}
            </p>
          </div>
        );
      }}
    </AsyncBoundary>
  );
}
