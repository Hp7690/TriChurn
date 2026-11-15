import { Activity, AlertOctagon, CheckCircle2, CircleDashed, CircleSlash, Hourglass } from 'lucide-react';
import type { ReactNode } from 'react';
import { Link } from 'react-router-dom';
import { LifecycleCustomersChart } from '../charts/LifecycleCharts';
import { AsyncBoundary } from '../components/AsyncBoundary';
import { Card } from '../components/Card';
import { EmptyState } from '../components/EmptyState';
import { ExperienceStatusBadge, STATUS_ORDER, statusLabel } from '../components/ExperienceStatusBadge';
import { KpiCard, type KpiTone } from '../components/KpiCard';
import { PageHeader } from '../components/PageHeader';
import { useAsync } from '../hooks/useAsync';
import { experienceApi, type ExperienceApi } from '../services/experienceService';
import type { AvailabilityResponse, ModuleKey, ModuleStatus, ModuleStatusInfo } from '../types/experience';
import { formatNumber } from '../utils/format';

const STATUS_TILES: Record<ModuleStatus, { icon: typeof Activity; tone: KpiTone }> = {
  AVAILABLE: { icon: CheckCircle2, tone: 'success' },
  PARTIALLY_AVAILABLE: { icon: Hourglass, tone: 'brand' },
  BLOCKED_BY_MISSING_DATA: { icon: CircleSlash, tone: 'default' },
  DISABLED: { icon: CircleDashed, tone: 'default' },
  VALIDATION_FAILED: { icon: AlertOctagon, tone: 'danger' },
};

function num(metrics: Record<string, unknown> | null, key: string): number | null {
  const v = metrics?.[key];
  return typeof v === 'number' ? v : null;
}

/** A few headline figures for modules that are AVAILABLE. Every value comes straight from the API response. */
function keyMetrics(m: ModuleStatusInfo): Array<{ label: string; value: string }> {
  const x = m.metrics;
  if (!x) return [];
  const out: Array<{ label: string; value: string }> = [];
  const add = (label: string, value: number | null, suffix = '') => {
    if (value !== null) out.push({ label, value: `${formatNumber(value)}${suffix}` });
  };
  switch (m.module) {
    case 'feedback':
      add('Records', num(x, 'records'));
      add('Human-labelled', num(x, 'labelled_records'));
      break;
    case 'complaints': {
      add('Tickets', num(x, 'tickets_total'));
      const sla = x.sla as { breach_rate_pct: number | null } | undefined;
      if (sla?.breach_rate_pct != null) out.push({ label: 'SLA breach rate', value: `${sla.breach_rate_pct}%` });
      break;
    }
    case 'nps':
      add('NPS', num(x, 'value'));
      add('Valid responses', num(x, 'valid_responses'));
      break;
    case 'csat':
      add('CSAT', num(x, 'value'), '%');
      add('Valid responses', num(x, 'valid_responses'));
      break;
    case 'journey':
      add('Events', num(x, 'events_total'));
      add('Customers', num(x, 'customers'));
      break;
    case 'sentiment': {
      const model = x.model as { name: string; version: string } | undefined;
      if (model) out.push({ label: 'Model', value: `${model.name} v${model.version}` });
      add('Labelled records', num(x, 'labelled_records'));
      break;
    }
    default:
      break;
  }
  if (x.low_sample === true) out.push({ label: 'Sample', value: 'Low sample: interpret with caution' });
  return out;
}

export function ModuleCard({ module }: { module: ModuleStatusInfo }) {
  const active = module.status === 'AVAILABLE';
  const metrics = keyMetrics(module);
  return (
    <article
      aria-label={module.title}
      data-module={module.module}
      className="flex flex-col rounded-xl border border-slate-200 bg-surface p-5 shadow-sm"
    >
      <header className="flex flex-wrap items-start justify-between gap-2">
        <h3 className="text-base font-semibold text-slate-900">{module.title}</h3>
        <ExperienceStatusBadge status={module.status} />
      </header>
      {module.reason && <p className="mt-3 text-sm text-slate-700">{module.reason}</p>}
      {active && metrics.length > 0 && (
        <dl className="mt-3 grid grid-cols-2 gap-3">
          {metrics.map((k) => (
            <div key={k.label}>
              <dt className="text-xs text-slate-500">{k.label}</dt>
              <dd className="text-lg font-semibold tabular-nums text-slate-900">{k.value}</dd>
            </div>
          ))}
        </dl>
      )}
      {module.validation && (
        <p className="mt-3 text-xs text-slate-600">
          Validation: {formatNumber(module.validation.rows_valid)} of {formatNumber(module.validation.rows_total)} rows valid ·{' '}
          {module.validation.error_count} error(s) · {module.validation.warning_count} warning(s)
        </p>
      )}
      {!active && (
        <div className="mt-4 rounded-lg bg-slate-50 p-3">
          <p className="text-xs font-semibold text-slate-500">What is needed to activate</p>
          <ul className="mt-1 list-disc space-y-1 pl-5 text-sm text-slate-700">
            {module.requirements.needs.map((need) => (
              <li key={need}>{need}</li>
            ))}
          </ul>
          {module.requirements.required_columns.length > 0 && (
            <p className="mt-2 text-xs text-slate-600">
              Required columns:{' '}
              {module.requirements.required_columns.map((c) => (
                <code key={c} className="mr-1 rounded bg-surface px-1 py-0.5 text-[11px] text-slate-800">
                  {c}
                </code>
              ))}
            </p>
          )}
          <p className="mt-2 text-xs text-slate-500">{module.requirements.note}</p>
        </div>
      )}
    </article>
  );
}

function Section({ id, title, description, children }: { id: string; title: string; description?: string; children: ReactNode }) {
  return (
    <section aria-labelledby={id} className="space-y-3">
      <div>
        <h2 id={id} className="text-lg font-semibold text-slate-900">
          {title}
        </h2>
        {description && <p className="text-sm text-slate-600">{description}</p>}
      </div>
      {children}
    </section>
  );
}

function find(data: AvailabilityResponse, key: ModuleKey): ModuleStatusInfo | undefined {
  return data.modules.find((m) => m.module === key);
}

function Cards({ data, keys }: { data: AvailabilityResponse; keys: ModuleKey[] }) {
  const items = keys.map((k) => find(data, k)).filter((m): m is ModuleStatusInfo => Boolean(m));
  return (
    <div className={items.length > 1 ? 'grid gap-4 lg:grid-cols-2' : 'grid gap-4'}>
      {items.map((m) => (
        <ModuleCard key={m.module} module={m} />
      ))}
    </div>
  );
}

function DataQualitySection({ data }: { data: AvailabilityResponse }) {
  const customer = data.data_quality.customer_dataset;
  const datasets = Object.entries(data.data_quality.datasets);
  const show = (v: number | null) => (v === null ? 'n/a' : formatNumber(v));
  return (
    <div className="grid gap-4 lg:grid-cols-2">
      <Card title="Customer dataset" description="The structured table used by the lifecycle proxy.">
        {customer ? (
          <dl className="grid grid-cols-2 gap-3 text-sm">
            {[
              ['Source file', customer.source],
              ['Rows', show(customer.rows)],
              ['Columns', show(customer.columns)],
              ['Duplicate customer IDs', show(customer.duplicate_customer_ids)],
              ['Missing or invalid tenure', show(customer.missing_tenure_or_invalid)],
              ['Missing TotalCharges', show(customer.missing_total_charges)],
              ['Missing MonthlyCharges', show(customer.missing_monthly_charges)],
              ['Missing Churn label', show(customer.missing_churn_label)],
            ].map(([label, value]) => (
              <div key={label}>
                <dt className="text-xs text-slate-500">{label}</dt>
                <dd className="font-semibold tabular-nums text-slate-900">{value}</dd>
              </div>
            ))}
          </dl>
        ) : (
          <EmptyState title="Customer dataset not available" description="Lifecycle data-quality figures need the customer CSV." />
        )}
      </Card>
      <Card title="Experience datasets" description="Validation of datasets configured in configs/experience.yaml.">
        <table className="w-full text-left text-sm">
          <thead className="text-xs text-slate-500">
            <tr>
              <th scope="col" className="py-1 pr-2">Dataset</th>
              <th scope="col" className="py-1 pr-2">Rows</th>
              <th scope="col" className="py-1 pr-2">Valid</th>
              <th scope="col" className="py-1 pr-2">Errors</th>
              <th scope="col" className="py-1">Warnings</th>
            </tr>
          </thead>
          <tbody className="divide-y divide-slate-100">
            {datasets.map(([name, v]) => (
              <tr key={name}>
                <th scope="row" className="py-2 pr-2 font-medium capitalize text-slate-800">{name}</th>
                {v ? (
                  <>
                    <td className="py-2 pr-2 tabular-nums">{formatNumber(v.rows_total)}</td>
                    <td className="py-2 pr-2 tabular-nums">{formatNumber(v.rows_valid)}</td>
                    <td className="py-2 pr-2 tabular-nums">{v.error_count}</td>
                    <td className="py-2 tabular-nums">{v.warning_count}</td>
                  </>
                ) : (
                  <td colSpan={4} className="py-2 text-slate-500">Not configured: nothing to validate</td>
                )}
              </tr>
            ))}
          </tbody>
        </table>
      </Card>
    </div>
  );
}

export function ExperiencePage({ api = experienceApi }: { api?: ExperienceApi }) {
  const state = useAsync(() => api.getAvailability(), [api]);
  return (
    <>
      <PageHeader
        title="Experience Command Center"
        description="Customer experience, feedback, complaint, satisfaction and lifecycle intelligence. A module shows figures only when real data supports it."
      />
      <div role="note" className="mb-6 rounded-lg border border-slate-200 bg-slate-50 px-4 py-3 text-sm text-slate-700">
        <strong className="font-semibold">Data source:</strong> live from <code>{api.baseUrl}</code>. Nothing on this page is mock data. The
        IBM Telco dataset has no feedback text, tickets, survey scores or event timestamps, so modules that need them stay blocked until real
        datasets are configured.
      </div>
      <AsyncBoundary state={state} errorTitle="Unable to load experience availability.">
        {(data) => (
          <div className="space-y-8">
            {data.config_error && (
              <div role="alert" className="rounded-lg border border-rose-200 bg-rose-50 px-4 py-3 text-sm text-rose-900">
                The experience configuration is invalid: {data.config_error}
              </div>
            )}

            <Section id="exp-availability" title="Experience data availability" description="Status of every Phase 13 module.">
              <div className="grid gap-4 sm:grid-cols-2 lg:grid-cols-5">
                {STATUS_ORDER.map((s) => (
                  <KpiCard key={s} label={statusLabel(s)} value={String(data.summary[s] ?? 0)} icon={STATUS_TILES[s].icon} tone={STATUS_TILES[s].tone} />
                ))}
              </div>
              <Card>
                <table className="w-full text-left text-sm">
                  <caption className="sr-only">Module availability</caption>
                  <thead className="text-xs text-slate-500">
                    <tr>
                      <th scope="col" className="py-1 pr-3">Module</th>
                      <th scope="col" className="py-1 pr-3">Status</th>
                      <th scope="col" className="py-1">Why</th>
                    </tr>
                  </thead>
                  <tbody className="divide-y divide-slate-100">
                    {data.modules.map((m) => (
                      <tr key={m.module}>
                        <th scope="row" className="py-2 pr-3 font-medium text-slate-900">{m.title}</th>
                        <td className="py-2 pr-3"><ExperienceStatusBadge status={m.status} /></td>
                        <td className="py-2 text-slate-600">{m.reason ?? 'Data present and validated.'}</td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </Card>
            </Section>

            <Section id="exp-lifecycle" title="Customer lifecycle overview" description="Tenure-based proxy: how long customers have stayed, not what they did.">
              {data.lifecycle_summary ? (
                <Card
                  title={`${formatNumber(data.lifecycle_summary.customers_analysed)} customers by tenure group`}
                  description="TENURE PROXY · not an event-based customer journey."
                  actions={<Link to="/experience-lifecycle" className="text-sm font-medium text-brand-700 hover:underline">Open lifecycle analysis</Link>}
                >
                  <LifecycleCustomersChart groups={data.lifecycle_summary.groups} />
                </Card>
              ) : (
                <EmptyState title="Lifecycle overview unavailable" description={find(data, 'lifecycle')?.reason ?? 'No customer dataset is available.'} />
              )}
            </Section>

            <Section id="exp-feedback" title="Feedback data status"><Cards data={data} keys={['feedback']} /></Section>
            <Section id="exp-sentiment" title="Sentiment intelligence status"><Cards data={data} keys={['sentiment']} /></Section>
            <Section id="exp-complaints" title="Complaint intelligence status"><Cards data={data} keys={['complaints']} /></Section>
            <Section id="exp-surveys" title="NPS & CSAT availability"><Cards data={data} keys={['nps', 'csat']} /></Section>
            <Section id="exp-journey" title="Customer journey availability"><Cards data={data} keys={['journey']} /></Section>
            <Section id="exp-quality" title="Data quality summary"><DataQualitySection data={data} /></Section>

            <ul className="list-disc space-y-1 pl-5 text-xs text-slate-500">
              {data.notices.map((n) => (<li key={n}>{n}</li>))}
              <li>Generated at {data.generated_at}.</li>
            </ul>
          </div>
        )}
      </AsyncBoundary>
    </>
  );
}
