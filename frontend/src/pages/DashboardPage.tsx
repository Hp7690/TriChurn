import { Activity, AlertTriangle, Target, TrendingUp, Users, Wallet } from 'lucide-react';
import { Link, useNavigate } from 'react-router-dom';
import { ActionBenefitChart } from '../charts/ActionBenefitChart';
import { RiskDistributionChart } from '../charts/RiskDistributionChart';
import { SegmentChart } from '../charts/SegmentChart';
import { ValueAtRiskChart } from '../charts/ValueAtRiskChart';
import { AsyncBoundary } from '../components/AsyncBoundary';
import { Card } from '../components/Card';
import { CustomerTable } from '../components/CustomerTable';
import { KpiCard } from '../components/KpiCard';
import { PageHeader } from '../components/PageHeader';
import { PipelineStrip } from '../components/PipelineStrip';
import { RetentionActionCard } from '../components/RetentionActionCard';
import { useAsync } from '../hooks/useAsync';
import { useService } from '../services/ServiceContext';
import { formatCurrency, formatNumber, formatPercent } from '../utils/format';

export function DashboardPage() {
  const service = useService();
  const navigate = useNavigate();
  const state = useAsync(() => service.getDashboard(), [service]);

  return (
    <>
      <PageHeader
        title="Executive Dashboard"
        description="Portfolio-level view of churn risk, value at risk and the retention opportunities worth acting on."
      />
      <PipelineStrip />
      <AsyncBoundary
        state={state}
        isEmpty={(d) => d.metrics.totalCustomers === 0}
        emptyTitle="No customers scored yet"
        emptyDescription="Once customers are available from the data source, portfolio metrics will appear here."
      >
        {(d) => (
          <div className="space-y-6">
            <div className="grid gap-4 sm:grid-cols-2 xl:grid-cols-3">
              <KpiCard label="Total Customers" value={formatNumber(d.metrics.totalCustomers)} icon={Users} />
              <KpiCard
                label="High Risk Customers"
                value={formatNumber(d.metrics.highRiskCustomers)}
                hint={`${formatPercent(d.metrics.highRiskCustomers / d.metrics.totalCustomers)} of customers`}
                icon={AlertTriangle}
                tone="danger"
              />
              <KpiCard
                label="Avg Churn Probability"
                value={formatPercent(d.metrics.averageChurnProbability)}
                icon={Activity}
                tone="brand"
              />
              <KpiCard
                label="Value at Risk (VaR)"
                value={formatCurrency(d.metrics.totalValueAtRisk, d.currency ?? 'USD')}
                hint="Revenue at risk across all customers"
                icon={Wallet}
                tone="danger"
              />
              <KpiCard
                label="Retention Opportunities"
                value={formatNumber(d.metrics.retentionOpportunities)}
                hint="Customers with an 'Intervene' decision"
                icon={Target}
                tone="brand"
              />
              <KpiCard
                label="Expected Net Benefit"
                value={formatCurrency(d.metrics.expectedNetBenefit, d.currency ?? 'USD')}
                hint="Sum of ENB for intervention candidates"
                icon={TrendingUp}
                tone="success"
              />
            </div>

            <div className="grid gap-6 lg:grid-cols-12">
              <Card className="lg:col-span-7" title="Churn Risk Distribution" description="Customers by predicted risk band">
                <RiskDistributionChart data={d.riskDistribution} />
              </Card>
              <Card className="lg:col-span-5" title="Customer Segment Distribution" description="Locked Phase 5 segments (K = 3)">
                <SegmentChart data={d.segmentProfiles} />
              </Card>
              <Card className="lg:col-span-7" title="Revenue / Value at Risk" description="Total CLV versus value at risk, by risk band">
                <ValueAtRiskChart data={d.exposureByRiskBand} currency={d.currency} />
              </Card>
              <Card className="lg:col-span-5" title="Retention Opportunity" description="Expected benefit by recommended action">
                <ActionBenefitChart data={d.actionSummary} currency={d.currency} />
              </Card>
            </div>

            <Card title="Recommended Actions" description="Intervention candidates grouped by best action">
              <div className="grid gap-4 sm:grid-cols-2 xl:grid-cols-4">
                {d.actionSummary.map((a) => (
                  <RetentionActionCard
                    key={a.actionId}
                    name={a.action}
                    cost={a.averageCost}
                    successRate={a.successRate}
                    customers={a.customers}
                    expectedBenefit={a.expectedBenefit}
                    currency={d.currency ?? 'USD'}
                  />
                ))}
              </div>
            </Card>

            <Card
              title="Recent High-Risk Customers"
              description="Most recently scored customers in the High risk band"
              actions={
                <Link to="/customers?risk=High" className="text-sm font-medium text-brand-700 hover:underline">
                  View all high-risk →
                </Link>
              }
            >
              {d.recentHighRisk.length === 0 ? (
                <p className="rounded-lg bg-sunken px-4 py-6 text-center text-sm text-slate-600">No high-risk customers right now.</p>
              ) : (
                <CustomerTable
                  rows={d.recentHighRisk}
                  caption="Recent high-risk customers"
                  onSelect={(id) => navigate(`/customers/${encodeURIComponent(id)}`)}
                />
              )}
            </Card>
          </div>
        )}
      </AsyncBoundary>
    </>
  );
}
