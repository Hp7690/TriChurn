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
  Opportunity,
  OpportunityQuery,
  OpportunitiesSummary,
  Paged,
  RiskCustomer,
  RiskCustomerQuery,
  RiskSummary,
  Summary,
} from '../../types/revenue';

/** Data-access port for Phase 12. Application code has no mock mode: the only implementation is HTTP. */
export interface RevenueProvider {
  readonly name: string;
  summary(): Promise<Summary>;
  clvSummary(): Promise<ClvSummary>;
  clvCustomers(q?: ClvCustomerQuery): Promise<Paged<ClvCustomer>>;
  clvSegments(): Promise<ClvSegments>;
  riskSummary(): Promise<RiskSummary>;
  riskCustomers(q?: RiskCustomerQuery): Promise<Paged<RiskCustomer>>;
  opportunitiesSummary(): Promise<OpportunitiesSummary>;
  opportunities(q?: OpportunityQuery): Promise<Paged<Opportunity>>;
  cohortSummary(): Promise<CohortSummary>;
  cohortTenure(): Promise<CohortTenure>;
  forecastReadiness(): Promise<ForecastReadiness>;
  forecastValidate(rows: ForecastRowInput[], runBacktest?: boolean): Promise<ForecastReadiness>;
  availability(): Promise<Availability>;
}

export class RevenueApiError extends Error {
  constructor(
    public readonly code: string,
    message: string,
    public readonly status: number,
  ) {
    super(message);
    this.name = 'RevenueApiError';
  }
}
