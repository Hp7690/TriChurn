/** TEST-ONLY fixtures shaped like the Phase 13 API responses. They never ship in the app bundle. */
import type {
  AvailabilityResponse,
  LifecycleGroup,
  LifecycleResponse,
  ModuleKey,
  ModuleStatusInfo,
} from '../types/experience';

const NEEDS: Record<ModuleKey, string[]> = {
  lifecycle: ['A customer table with a numeric tenure (months) column.'],
  feedback: ['A CSV or JSON file of real customer feedback with feedback_id, customer_id, feedback_text and submitted_at.'],
  sentiment: ['A validated feedback dataset (above).', 'A documented model registered in code.'],
  complaints: ['A real ticket export with ticket_id, customer_id, category, severity, status and created_at.'],
  nps: ['NPS survey responses with response_id, customer_id, score and survey_date.'],
  csat: ['CSAT survey responses with response_id, customer_id, score and survey_date.'],
  journey: ['Timestamped events with customer_id, event_type, event_timestamp and channel.'],
};

export function moduleInfo(module: ModuleKey, patch: Partial<ModuleStatusInfo> = {}): ModuleStatusInfo {
  const blocked = module !== 'lifecycle';
  return {
    module,
    title: `${module} title`,
    status: blocked ? 'BLOCKED_BY_MISSING_DATA' : 'AVAILABLE',
    reason: blocked ? `No '${module}' dataset is configured.` : null,
    dataset_configured: false,
    requirements: {
      needs: NEEDS[module],
      note: `${module} note`,
      dataset_kind: blocked ? module : null,
      required_columns: blocked ? [`${module}_id`, 'customer_id'] : ['tenure'],
      optional_columns: [],
    },
    validation: null,
    metrics: null,
    generated_at: '2026-11-11T12:00:00+00:00',
    ...patch,
  };
}

export const MODULE_KEYS: ModuleKey[] = ['lifecycle', 'feedback', 'sentiment', 'complaints', 'nps', 'csat', 'journey'];

export function availability(patch: Partial<AvailabilityResponse> = {}): AvailabilityResponse {
  return {
    enabled: true,
    config_error: null,
    summary: { AVAILABLE: 1, PARTIALLY_AVAILABLE: 0, BLOCKED_BY_MISSING_DATA: 6, DISABLED: 0, VALIDATION_FAILED: 0 },
    modules: MODULE_KEYS.map((k) => moduleInfo(k)),
    lifecycle_summary: {
      label: 'TENURE_PROXY',
      is_event_based: false,
      customers_analysed: 120,
      groups: [
        { name: 'New Customer', customers: 70, share_pct: 58.33 },
        { name: 'Long-Term Customer', customers: 50, share_pct: 41.67 },
      ],
    },
    data_quality: {
      datasets: { feedback: null, tickets: null, nps: null, csat: null, events: null },
      customer_dataset: {
        source: 'customers.csv',
        rows: 120,
        columns: 6,
        duplicate_customer_ids: 0,
        missing_tenure_or_invalid: 0,
        missing_total_charges: 3,
        missing_monthly_charges: 0,
        missing_churn_label: 0,
      },
    },
    notices: ['Modules marked BLOCKED_BY_MISSING_DATA need the real datasets listed under each module.'],
    generated_at: '2026-11-11T12:00:00+00:00',
    ...patch,
  };
}

function group(name: string, min: number, max: number | null, customers: number, patch: Partial<LifecycleGroup> = {}): LifecycleGroup {
  return {
    name,
    min_months: min,
    max_months: max,
    customers,
    share_pct: 50,
    churn: { known_labels: customers, churned: 10, churn_rate_pct: 40, rate_withheld_reason: null },
    contract_distribution: { 'Month-to-month': customers - 5, 'One year': 5 },
    monthly_charges: { count: customers, mean: 61.5, median: 60, min: 20, max: 110, sum: 4000 },
    total_charges: { count: customers - 1, mean: 900.25, median: 800, min: 20, max: 5000, sum: 90000, missing: 1 },
    risk: null,
    ...patch,
  };
}

export function lifecycle(patch: Partial<LifecycleResponse> = {}): LifecycleResponse {
  return {
    status: 'AVAILABLE',
    label: 'TENURE_PROXY',
    is_event_based: false,
    reason: null,
    methodology: 'Customers are grouped by tenure. This is a tenure-based lifecycle proxy, not an event-based customer journey.',
    thresholds: [
      { name: 'New Customer', min_months: 0, max_months: 6 },
      { name: 'Long-Term Customer', min_months: 6, max_months: null },
    ],
    customers_total: 120,
    customers_analysed: 118,
    excluded: { total: 2, invalid_or_missing_tenure: 2 },
    columns_used: ['tenure', 'Contract', 'Churn'],
    columns_missing: ['MonthlyCharges'],
    groups: [
      group('New Customer', 0, 6, 70),
      group('Long-Term Customer', 6, null, 48, {
        churn: { known_labels: 48, churned: 2, churn_rate_pct: null, rate_withheld_reason: 'Fewer than 50 labelled customers in this group.' },
      }),
    ],
    overall: { churn_labels_known: 118, churned: 12, churn_rate_pct: 10.17 },
    risk_distribution: { status: 'BLOCKED_BY_MISSING_DATA', bands: null, reason: 'No existing churn probabilities are available.' },
    assumptions: ['Tenure is measured in months as recorded in the dataset.'],
    limitations: ['This is a tenure proxy.'],
    source: 'Customer dataset: customers.csv',
    generated_at: '2026-11-11T12:00:00+00:00',
    ...patch,
  };
}
