import { ActionBenefitChart } from '../charts/ActionBenefitChart';
import { AsyncBoundary } from '../components/AsyncBoundary';
import { Card } from '../components/Card';
import { CustomerRankList } from '../components/CustomerRankList';
import { KpiCard } from '../components/KpiCard';
import { PageHeader } from '../components/PageHeader';
import { RetentionActionCard } from '../components/RetentionActionCard';
import { Target, TrendingUp } from 'lucide-react';
import { useAsync } from '../hooks/useAsync';
import { useService } from '../services/ServiceContext';
import { formatCurrency, formatNumber, formatPercent } from '../utils/format';

export function InsightsPage() {
  const service = useService();
  const state = useAsync(() => service.getInsights(), [service]);

  return (
    <>
      <PageHeader
        title="Retention Insights"
        description="Where to focus retention effort, based on the existing business-engine outputs for each customer."
      />
      <AsyncBoundary state={state} isEmpty={(i) => i.actionSummary.length === 0 && i.highestVar.length === 0} emptyTitle="No retention insights available">
        {(i) => (
          <div className="space-y-6">
            <div className="grid gap-4 sm:grid-cols-2">
              <KpiCard label="Intervention Opportunities" value={formatNumber(i.interventionCount)} icon={Target} tone="brand" />
              <KpiCard label="Total Expected Benefit" value={formatCurrency(i.totalExpectedBenefit, i.currency ?? 'USD', 2)} icon={TrendingUp} tone="success" />
            </div>

            <div className="grid gap-6 lg:grid-cols-3">
              <Card title="Highest-value customers at risk" description="Medium/High risk, ranked by CLV">
                <CustomerRankList items={i.highestValueAtRisk} metricLabel="CLV" metric={(r) => formatCurrency(r.business.clv, r.business.currency)} />
              </Card>
              <Card title="Highest-VaR customers" description="Ranked by value at risk">
                <CustomerRankList items={i.highestVar} metricLabel="VaR" metric={(r) => formatCurrency(r.business.valueAtRisk, r.business.currency)} />
              </Card>
              <Card title="Highest-ENB opportunities" description="Intervention candidates ranked by expected net benefit">
                <CustomerRankList items={i.highestEnb} metricLabel="ENB" metric={(r) => formatCurrency(r.business.expectedNetBenefit, r.business.currency)} />
              </Card>
            </div>

            <Card title="Action Summary" description="Recommended retention actions across intervention candidates">
              <div className="overflow-x-auto rounded-lg border border-slate-200">
                <table className="w-full min-w-[560px] text-sm">
                  <caption className="sr-only">Action summary</caption>
                  <thead className="bg-slate-50 text-xs text-slate-600">
                    <tr>
                      <th scope="col" className="px-3 py-2.5 text-left">Action</th>
                      <th scope="col" className="px-3 py-2.5 text-right">Customers</th>
                      <th scope="col" className="px-3 py-2.5 text-right">Average Cost</th>
                      <th scope="col" className="px-3 py-2.5 text-right">Success Rate</th>
                      <th scope="col" className="px-3 py-2.5 text-right">Expected Benefit</th>
                    </tr>
                  </thead>
                  <tbody className="divide-y divide-slate-100">
                    {i.actionSummary.map((a) => (
                      <tr key={a.actionId}>
                        <td className="px-3 py-2.5 font-medium">{a.action}</td>
                        <td className="px-3 py-2.5 text-right tabular-nums">{a.customers}</td>
                        <td className="px-3 py-2.5 text-right tabular-nums">{formatCurrency(a.averageCost, i.currency ?? 'USD')}</td>
                        <td className="px-3 py-2.5 text-right tabular-nums">{formatPercent(a.successRate, 0)}</td>
                        <td className="px-3 py-2.5 text-right tabular-nums">{formatCurrency(a.expectedBenefit, i.currency ?? 'USD', 2)}</td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            </Card>

            <div className="grid gap-6 lg:grid-cols-2">
              <Card title="Expected Benefit by Action">
                <ActionBenefitChart data={i.actionSummary} currency={i.currency} />
              </Card>
              <Card title="Recommended Retention Actions">
                <div className="grid gap-4 sm:grid-cols-2">
                  {i.actionSummary.map((a) => (
                    <RetentionActionCard
                      key={a.actionId}
                      name={a.action}
                      cost={a.averageCost}
                      successRate={a.successRate}
                      customers={a.customers}
                      expectedBenefit={a.expectedBenefit}
                      currency={i.currency ?? 'USD'}
                    />
                  ))}
                </div>
              </Card>
            </div>
          </div>
        )}
      </AsyncBoundary>
    </>
  );
}
