import { AsyncBoundary } from '../components/AsyncBoundary';
import { Card } from '../components/Card';
import { MetricCard } from '../components/MetricCard';
import { PageHeader } from '../components/PageHeader';
import { useAsync } from '../hooks/useAsync';
import { useService } from '../services/ServiceContext';
import type { ChurnModelMetrics } from '../types';
import { formatMetric } from '../utils/format';

const METRIC_LABELS: Array<[keyof ChurnModelMetrics, string]> = [
  ['rocAuc', 'ROC-AUC'],
  ['prAuc', 'PR-AUC'],
  ['brierScore', 'Brier Score'],
  ['logLoss', 'Log Loss'],
  ['accuracy', 'Accuracy'],
  ['precision', 'Precision'],
  ['recall', 'Recall'],
  ['f1', 'F1'],
];

export function ModelPage() {
  const service = useService();
  const state = useAsync(() => service.getModelInfo(), [service]);

  return (
    <>
      <PageHeader title="System & Model Information" description="Read-only information about the locked model artifacts behind this dashboard." />
      <AsyncBoundary state={state}>
        {(m) => (
          <div className="space-y-6">
            <Card title="Phase 2 — Churn Prediction Model" description="Locked evaluation metrics. These values are read-only.">
              <div className="mb-4 grid gap-3 sm:grid-cols-2">
                <MetricCard label="Model version" value={m.churn.version} />
                <MetricCard label="Artifact" value={<span className="break-all text-sm">{m.churn.artifact}</span>} />
              </div>
              <div className="grid gap-3 sm:grid-cols-2 lg:grid-cols-4">
                {METRIC_LABELS.map(([key, label]) => (
                  <MetricCard key={key} label={label} value={formatMetric(m.churn.metrics[key])} />
                ))}
              </div>
            </Card>

            <Card title="Phase 5 — Customer Segmentation" description="Segmentation is based on the locked Phase 5 artifact; the frontend never re-clusters customers.">
              <div className="grid gap-3 sm:grid-cols-3">
                <MetricCard label="K (segments)" value={m.segmentation.k} />
                <MetricCard label="Seed" value={m.segmentation.seed} />
                <MetricCard label="Version" value={m.segmentation.version} />
              </div>
              <h3 className="mb-2 mt-5 text-sm font-semibold text-slate-800">Features</h3>
              <ul className="flex flex-wrap gap-2">
                {m.segmentation.features.map((f) => (
                  <li key={f} className="rounded-md bg-slate-100 px-2.5 py-1 font-mono text-xs text-slate-800">{f}</li>
                ))}
              </ul>
              <p className="mt-3 text-xs text-slate-500">Artifact: {m.segmentation.artifact}</p>
            </Card>

            <Card title="Data source">
              <p className="text-sm text-slate-700">
                {m.dataMode === 'mock'
                  ? 'This dashboard is running on deterministic DEMO data from the mock provider. Model values above are the locked reference values; customer-level numbers are illustrative.'
                  : 'This dashboard is connected to the live API.'}
              </p>
            </Card>
          </div>
        )}
      </AsyncBoundary>
    </>
  );
}
