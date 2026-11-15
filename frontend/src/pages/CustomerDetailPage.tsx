import { Link, useParams } from 'react-router-dom';
import { ShapChart } from '../charts/ShapChart';
import { AsyncBoundary } from '../components/AsyncBoundary';
import { Card } from '../components/Card';
import { CustomerHeader } from '../components/CustomerHeader';
import { DecisionBadge } from '../components/DecisionBadge';
import { EmptyState } from '../components/EmptyState';
import { LoadingSkeleton } from '../components/LoadingSkeleton';
import { MetricCard } from '../components/MetricCard';
import { RetentionActionCard } from '../components/RetentionActionCard';
import { RiskBadge } from '../components/RiskBadge';
import { SegmentBadge } from '../components/SegmentBadge';
import { useAsync } from '../hooks/useAsync';
import { NotFoundError } from '../services/api/errors';
import { useService } from '../services/ServiceContext';
import { cn } from '../utils/cn';
import { formatCurrency, formatPercent, formatSigned } from '../utils/format';
import { splitDrivers } from '../utils/shap';

export function CustomerDetailPage() {
  const { customerId = '' } = useParams();
  const service = useService();
  const state = useAsync(() => service.getCustomer(decodeURIComponent(customerId)), [service, customerId]);

  if (state.status === 'error' && state.error instanceof NotFoundError) {
    return (
      <EmptyState
        title="Customer not found"
        description={`No customer with ID "${decodeURIComponent(customerId)}" exists in the current data source.`}
        action={
          <Link to="/customers" className="btn btn-primary">
            Back to customers
          </Link>
        }
      />
    );
  }

  return (
    <AsyncBoundary state={state} skeleton={<LoadingSkeleton variant="page" />}>
      {(r) => {
        const { positive, negative } = splitDrivers(r.explanation.contributions);
        const b = r.business;
        return (
          <div className="space-y-6">
            <CustomerHeader result={r} />

            <Card title="Customer Overview">
              <div className="grid gap-3 sm:grid-cols-2 lg:grid-cols-5">
                <MetricCard label="Churn probability" value={formatPercent(r.prediction.churnProbability)} />
                <MetricCard label="Predicted label" value={r.prediction.predictedLabel} />
                <MetricCard label="Risk band" value={<RiskBadge band={r.prediction.riskBand} />} />
                <MetricCard label="Segment" value={<SegmentBadge segmentId={r.segment.segmentId} label={r.segment.label} />} />
                <MetricCard label="Model version" value={r.prediction.modelVersion} />
              </div>
            </Card>

            <Card title="Business Value" description="Outputs of the retention engine for this customer">
              <div className="grid gap-3 sm:grid-cols-2 lg:grid-cols-5">
                <MetricCard label="CLV" value={formatCurrency(b.clv, b.currency)} />
                <MetricCard label="VaR" value={formatCurrency(b.valueAtRisk, b.currency)} />
                <MetricCard
                  label="ENB"
                  value={<span className={cn(b.expectedNetBenefit < 0 && 'text-rose-700')}>{formatCurrency(b.expectedNetBenefit, b.currency)}</span>}
                />
                <MetricCard label="Decision" value={<DecisionBadge decision={b.decision} />} />
                <MetricCard label="Best action" value={<span className="text-base">{b.bestAction?.name ?? 'No action'}</span>} />
              </div>
              <div className="mt-5 grid gap-6 lg:grid-cols-2">
                <div>
                  <h3 className="mb-2 text-sm font-semibold text-slate-800">Evaluated actions</h3>
                  <div className="overflow-x-auto rounded-lg border border-slate-200">
                    <table className="w-full min-w-[420px] text-sm">
                      <thead className="bg-slate-50 text-xs text-slate-600">
                        <tr>
                          <th scope="col" className="px-3 py-2 text-left">Action</th>
                          <th scope="col" className="px-3 py-2 text-right">Cost</th>
                          <th scope="col" className="px-3 py-2 text-right">Success</th>
                          <th scope="col" className="px-3 py-2 text-right">ENB</th>
                        </tr>
                      </thead>
                      <tbody className="divide-y divide-slate-100">
                        {b.actionOptions.map((o) => (
                          <tr key={o.action.id}>
                            <td className="px-3 py-2">{o.action.name}</td>
                            <td className="px-3 py-2 text-right tabular-nums">{formatCurrency(o.action.cost, b.currency)}</td>
                            <td className="px-3 py-2 text-right tabular-nums">{formatPercent(o.action.successRate, 0)}</td>
                            <td className={cn('px-3 py-2 text-right tabular-nums', o.expectedNetBenefit < 0 && 'text-rose-700')}>
                              {formatCurrency(o.expectedNetBenefit, b.currency)}
                            </td>
                          </tr>
                        ))}
                      </tbody>
                    </table>
                  </div>
                </div>
                <div>
                  {b.bestAction ? (
                    <RetentionActionCard
                      name={b.bestAction.name}
                      description={b.bestAction.description}
                      cost={b.bestAction.cost}
                      successRate={b.bestAction.successRate}
                      expectedBenefit={b.expectedNetBenefit}
                      currency={b.currency}
                    />
                  ) : (
                    <p className="rounded-lg bg-slate-50 p-4 text-sm text-slate-700">
                      No evaluated action has a positive expected net benefit, so the decision is not to intervene.
                    </p>
                  )}
                  <Link
                    to={`/what-if?customer=${encodeURIComponent(r.prediction.customerId)}`}
                    className="mt-3 inline-block text-sm font-medium text-brand-700 hover:underline"
                  >
                    Explore a what-if scenario →
                  </Link>
                </div>
              </div>
            </Card>

            <Card
              title="Explainability"
              description="SHAP-style feature contributions in log-odds, as produced by Phase 3. Red pushes towards churn; green pushes away."
            >
              <ShapChart contributions={r.explanation.contributions} />
              <p className="mt-2 text-xs text-slate-500">Base value: {formatSigned(r.explanation.baseValue)} log-odds</p>
              <div className="mt-4 grid gap-4 md:grid-cols-2">
                <div>
                  <h3 className="mb-2 text-sm font-semibold text-rose-800">Top churn drivers (increase risk)</h3>
                  <ul className="space-y-1 text-sm">
                    {positive.length === 0 && <li className="text-slate-600">None.</li>}
                    {positive.map((c) => (
                      <li key={c.feature} className="flex justify-between gap-2">
                        <span>{c.feature} = {c.featureValue}</span>
                        <span className="tabular-nums text-rose-700">{formatSigned(c.contribution)}</span>
                      </li>
                    ))}
                  </ul>
                </div>
                <div>
                  <h3 className="mb-2 text-sm font-semibold text-emerald-800">Top protective factors (reduce risk)</h3>
                  <ul className="space-y-1 text-sm">
                    {negative.length === 0 && <li className="text-slate-600">None.</li>}
                    {negative.map((c) => (
                      <li key={c.feature} className="flex justify-between gap-2">
                        <span>{c.feature} = {c.featureValue}</span>
                        <span className="tabular-nums text-emerald-700">{formatSigned(c.contribution)}</span>
                      </li>
                    ))}
                  </ul>
                </div>
              </div>
            </Card>

            <Card title="Customer Profile" description="Phase 5 clustering features and supporting attributes">
              <dl className="grid gap-3 text-sm sm:grid-cols-2 lg:grid-cols-4">
                {[
                  ['Tenure', `${r.customer.tenure} months`],
                  ['Monthly charges', formatCurrency(r.customer.monthlyCharges, b.currency)],
                  ['Total charges', formatCurrency(r.customer.totalCharges, b.currency)],
                  ['Service count', String(r.customer.serviceCount)],
                  ['Contract risk', String(r.customer.contractRisk)],
                  ['Contract', r.customer.contractType],
                  ['Internet service', r.customer.internetService],
                  ['Payment method', r.customer.paymentMethod],
                ].map(([k, v]) => (
                  <div key={k}>
                    <dt className="text-xs text-slate-500">{k}</dt>
                    <dd className="font-medium text-slate-900">{v}</dd>
                  </div>
                ))}
              </dl>
            </Card>
          </div>
        );
      }}
    </AsyncBoundary>
  );
}
