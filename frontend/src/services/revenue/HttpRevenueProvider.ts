import type {
  Availability,
  ClvCustomer,
  ClvCustomerQuery,
  ClvSegments,
  ClvSummary,
  CohortSummary,
  CohortTenure,
  ForecastReadiness,
  ForecastRowInput,
  OpportunitiesSummary,
  Opportunity,
  OpportunityQuery,
  Paged,
  RiskCustomer,
  RiskCustomerQuery,
  RiskSummary,
  Summary,
} from '../../types/revenue';
import type { RevenueProvider } from './RevenueProvider';
import { RevenueApiError } from './RevenueProvider';

export const REVENUE_PREFIX = '/api/v1/revenue-intelligence';

type Params = Record<string, string | number | boolean | undefined>;

function query(params?: Params): string {
  if (!params) return '';
  const usp = new URLSearchParams();
  for (const [k, v] of Object.entries(params)) if (v !== undefined && v !== '') usp.set(k, String(v));
  const s = usp.toString();
  return s ? `?${s}` : '';
}

export async function toApiError(response: Response): Promise<RevenueApiError> {
  let code = 'HTTP_ERROR';
  let message = `Request failed (${response.status}).`;
  try {
    const body: unknown = await response.json();
    const err = (body as { error?: { code?: string; message?: string } }).error;
    if (err?.message) {
      code = err.code ?? code;
      message = err.message;
    } else if ((body as { detail?: unknown }).detail !== undefined) {
      code = 'INVALID_INPUT';
      message = 'The request was not valid.';
    }
  } catch {
    /* non-JSON error body: keep the generic message */
  }
  return new RevenueApiError(code, message, response.status);
}

export class HttpRevenueProvider implements RevenueProvider {
  readonly name = 'HttpRevenueProvider';
  constructor(private readonly options: { baseUrl: string; timeoutMs?: number }) {}

  private async request<T>(path: string, init?: RequestInit, params?: Params): Promise<T> {
    const controller = new AbortController();
    const timer = setTimeout(() => controller.abort(), this.options.timeoutMs ?? 60000);
    try {
      const response = await fetch(`${this.options.baseUrl}${REVENUE_PREFIX}${path}${query(params)}`, {
        ...init,
        signal: controller.signal,
        headers: { Accept: 'application/json', ...(init?.body ? { 'Content-Type': 'application/json' } : {}) },
      });
      if (!response.ok) throw await toApiError(response);
      return (await response.json()) as T;
    } catch (error) {
      if (error instanceof RevenueApiError) throw error;
      if (error instanceof DOMException && error.name === 'AbortError')
        throw new RevenueApiError('TIMEOUT', 'The request timed out.', 0);
      throw new RevenueApiError('NETWORK_ERROR', 'The API could not be reached.', 0);
    } finally {
      clearTimeout(timer);
    }
  }

  summary = () => this.request<Summary>('/summary');
  clvSummary = () => this.request<ClvSummary>('/clv/summary');
  clvCustomers = (q?: ClvCustomerQuery) =>
    this.request<Paged<ClvCustomer>>(
      '/clv/customers', undefined, q as Params);
  clvSegments = () => this.request<ClvSegments>('/clv/segments');
  riskSummary = () => this.request<RiskSummary>('/revenue-at-risk/summary');
  riskCustomers = (q?: RiskCustomerQuery) =>
    this.request<Paged<RiskCustomer>>(
      '/revenue-at-risk/customers', undefined, q as Params);
  opportunitiesSummary = () => this.request<OpportunitiesSummary>('/opportunities/summary');
  opportunities = (q?: OpportunityQuery) =>
    this.request<Paged<Opportunity>>(
      '/opportunities/customers', undefined, q as Params);
  cohortSummary = () => this.request<CohortSummary>('/cohorts/summary');
  cohortTenure = () => this.request<CohortTenure>('/cohorts/tenure');
  forecastReadiness = () => this.request<ForecastReadiness>('/forecast/readiness');
  forecastValidate = (rows: ForecastRowInput[], runBacktest = false) =>
    this.request<ForecastReadiness>('/forecast/validate', {
      method: 'POST',
      body: JSON.stringify({ rows, run_backtest: runBacktest }),
    });
  availability = () => this.request<Availability>('/availability');
}
