import axios, { type AxiosInstance } from 'axios';
import type {
  CustomerQuery,
  DashboardData,
  HealthStatus,
  IntelligenceResult,
  ModelInfo,
  Page,
  RetentionAction,
  RetentionInsights,
  SegmentOverview,
  WhatIfInput,
  WhatIfResult,
} from '../../types';
import { API_ENDPOINTS, type HealthResponse } from '../api/contract';
import type { DataProvider } from '../api/DataProvider';
import { ApiError, NotFoundError } from '../api/errors';
import {
  loadLiveCustomers,
  type LiveCustomerFeatures,
} from './liveCustomerLoader';
import {
  buildDashboard,
  buildInsights,
  buildSegmentOverview,
  queryCustomers,
} from '../aggregations';
import { SEGMENT_META, SEGMENT_ORDER } from '../../utils/segments';

export interface FastAPIProviderOptions {
  baseUrl: string;
  timeoutMs?: number;
}

type ApiIntelligenceResponse = Record<string, unknown>;

export class FastAPIDataProvider implements DataProvider {
  readonly name = 'FastAPIDataProvider';
  readonly mode = 'live' as const;

  private readonly http: AxiosInstance;
  private readonly cache = new Map<string, IntelligenceResult>();
  private liveCustomers: LiveCustomerFeatures[] = [];
  private liveCustomersPromise!: Promise<void>;
  private liveCustomersScoringPromise: Promise<void> | null = null;
  private liveCustomersError: Error | null = null;

  constructor(options: FastAPIProviderOptions) {
    this.http = axios.create({
      baseURL: options.baseUrl,
      timeout: options.timeoutMs ?? 15000,
      headers: {
        'Content-Type': 'application/json',
      },
    });

    this.liveCustomersPromise = loadLiveCustomers().then((customers) => {
      if (customers.length === 0) {
        throw new Error('The live customer data file contains no customers.');
      }
      this.liveCustomers = customers;
    }).catch((error: unknown) => {
      this.liveCustomersError = error instanceof Error
        ? error
        : new Error('Unable to load the live customer data file.');
    });
  }

  private async ensureLiveCustomersAvailable(): Promise<void> {
    await this.liveCustomersPromise;
    if (this.liveCustomersError) {
      throw new ApiError(this.liveCustomersError.message);
    }
  }

  private async scoreLiveCustomers(): Promise<void> {
    await this.ensureLiveCustomersAvailable();
    if (!this.liveCustomersScoringPromise) {
      this.liveCustomersScoringPromise = (async () => {
        const batchSize = 4;
        for (let index = 0; index < this.liveCustomers.length; index += batchSize) {
          const batch = this.liveCustomers.slice(index, index + batchSize);
          await Promise.all(batch.map((customer) => this.getCustomer(customer.customerID)));
        }
      })().catch((error: unknown) => {
        this.liveCustomersScoringPromise = null;
        throw error;
      });
    }
    await this.liveCustomersScoringPromise;
  }

  private handleError(error: unknown): never {
    if (axios.isAxiosError(error)) {
      const status = error.response?.status;

      if (status === 404) {
        throw new NotFoundError('Customer was not found.');
      }

      const message =
        typeof error.response?.data?.error?.message === 'string'
          ? error.response.data.error.message
          : error.message || 'FastAPI request failed.';

      throw new ApiError(message, status);
    }

    throw error;
  }

  private async fetchIntelligence(customerId: string): Promise<IntelligenceResult> {
    await this.ensureLiveCustomersAvailable();

    const cached = this.cache.get(customerId);
    if (cached) return cached;

    try {
      const { data } = await this.http.post<ApiIntelligenceResponse>(
        API_ENDPOINTS.intelligence,
        {
          customer_id: customerId,
          features: (() => {
            const customer = this.liveCustomers.find((item) => item.customerID === customerId);

            if (!customer) {
              throw new NotFoundError('Customer was not found.');
            }

            return {
              tenure: customer.tenure,
              MonthlyCharges: customer.MonthlyCharges,
              TotalCharges: customer.TotalCharges,
              gender: customer.gender,
              SeniorCitizen: customer.SeniorCitizen,
              Partner: customer.Partner,
              Dependents: customer.Dependents,
              PhoneService: customer.PhoneService,
              MultipleLines: customer.MultipleLines,
              InternetService: customer.InternetService,
              OnlineSecurity: customer.OnlineSecurity,
              OnlineBackup: customer.OnlineBackup,
              DeviceProtection: customer.DeviceProtection,
              TechSupport: customer.TechSupport,
              StreamingTV: customer.StreamingTV,
              StreamingMovies: customer.StreamingMovies,
              Contract: customer.Contract,
              PaperlessBilling: customer.PaperlessBilling,
              PaymentMethod: customer.PaymentMethod,
            };
          })(),
        },
      );

      const result = this.mapIntelligence(data);
      this.cache.set(customerId, result);
      return result;
    } catch (error) {
      this.handleError(error);
    }
  }

  private mapIntelligence(data: ApiIntelligenceResponse): IntelligenceResult {
    const prediction = data.prediction as Record<string, unknown>;
    const explanation = data.explanation as Record<string, unknown>;
    const business = data.business as Record<string, unknown>;
    const segment = data.segment as Record<string, unknown>;

    const customerId = String(data.customer_id ?? prediction.customer_id ?? '');

    const churnProbability = Number(prediction.churn_probability ?? 0);

    const riskBandRaw = String(prediction.risk_band ?? 'MEDIUM').toUpperCase();
    const riskBand =
      ['HIGH', 'CRITICAL'].includes(riskBandRaw) ? 'High' :
      riskBandRaw === 'LOW' ? 'Low' :
      'Medium';

    const predictedLabel = prediction.predicted_churn === true ? 'Churn' : 'No Churn';

    const shapFeatures = Array.isArray(explanation.features)
      ? explanation.features
      : [];

    const contributions = shapFeatures
      .map((item) => {
        const feature = item as Record<string, unknown>;
        return {
          feature: String(feature.source_feature ?? feature.feature ?? ''),
          featureValue: String(feature.raw_value ?? feature.feature_value ?? ''),
          contribution: Number(feature.shap_value ?? feature.contribution ?? 0),
        };
      })
      .sort((a, b) => Math.abs(b.contribution) - Math.abs(a.contribution));

    const actionsRaw = Array.isArray(business.action_evaluations)
      ? business.action_evaluations
      : [];

    const actionOptions = actionsRaw.map((item) => {
      const evaluation = item as Record<string, unknown>;
      const actionRaw = (evaluation.action ?? evaluation) as Record<string, unknown>;

      return {
        action: {
          id: String(evaluation.action_id ?? actionRaw.id ?? ''),
          name: String(evaluation.name ?? actionRaw.name ?? ''),
          description: String(evaluation.description ?? actionRaw.description ?? ''),
          cost: Number(evaluation.cost ?? actionRaw.cost ?? 0),
          successRate: Number(
            evaluation.success_rate ?? actionRaw.success_rate ?? actionRaw.successRate ?? 0,
          ),
        },
        expectedNetBenefit: Number(
          evaluation.expected_net_benefit ??
            evaluation.expectedNetBenefit ??
            0,
        ),
      };
    });

    const bestActionId = String(
      business.recommended_action_id ?? 'no_action',
    );

    const bestAction =
      bestActionId === 'no_action'
        ? null
        : actionOptions.find((item) => item.action.id === bestActionId)?.action ??
          null;

    const decision =
      String(business.intervention_decision ?? 'DO_NOT_INTERVENE') ===
      'INTERVENE'
        ? 'Intervene'
        : 'Do not intervene';

    const segmentIdNumber = Number(segment.segment_id);
    const segmentId = SEGMENT_ORDER.find((id) => SEGMENT_META[id].clusterId === segmentIdNumber);
    if (!segmentId) {
      throw new ApiError(`Unknown segment cluster id "${String(segment.segment_id)}".`);
    }

    const segmentLabel = String(
      segment.segment_name ?? 'Low Value / High Risk',
    );

    const liveCustomer = this.liveCustomers.find(
      (item) => item.customerID === customerId,
    );

    const featureValue = (name: string): unknown =>
      shapFeatures.find(
        (item) =>
          String((item as Record<string, unknown>).source_feature ?? '') === name,
      )
        ? (shapFeatures.find(
            (item) =>
              String((item as Record<string, unknown>).source_feature ?? '') === name,
          ) as Record<string, unknown>).raw_value
        : undefined;

    const customer = {
      customerId,
      tenure: Number(liveCustomer?.tenure ?? featureValue('tenure') ?? 0),
      monthlyCharges: Number(liveCustomer?.MonthlyCharges ?? featureValue('MonthlyCharges') ?? 0),
      totalCharges: Number(liveCustomer?.TotalCharges ?? featureValue('TotalCharges') ?? 0),
      serviceCount: Number(featureValue('service_count') ?? 0),
      contractRisk: Number(featureValue('contract_risk') ?? 0),
      contractType: liveCustomer?.Contract ?? 'Month-to-month',
      internetService: (
        liveCustomer?.InternetService === 'No'
          ? 'None'
          : liveCustomer?.InternetService ?? 'DSL'
      ) as 'DSL' | 'Fiber optic' | 'None',
      techSupport: liveCustomer?.TechSupport === 'Yes',
      paymentMethod: (
        liveCustomer?.PaymentMethod === 'Bank transfer (automatic)'
          ? 'Bank transfer'
          : liveCustomer?.PaymentMethod === 'Credit card (automatic)'
            ? 'Credit card'
            : liveCustomer?.PaymentMethod ?? 'Electronic check'
      ) as 'Electronic check' | 'Mailed check' | 'Bank transfer' | 'Credit card',
    };

    return {
      customer,
      prediction: {
        customerId,
        churnProbability,
        predictedLabel,
        riskBand,
        modelVersion: String(prediction.model_version ?? '2.0.0'),
        scoredAt: new Date().toISOString().slice(0, 10),
      },
      explanation: {
        customerId,
        baseValue: Number(explanation.base_value ?? 0),
        contributions,
      },
      business: {
        customerId,
        currency: String(business.currency ?? 'USD').toUpperCase(),
        clv: Number(business.clv ?? 0),
        valueAtRisk: Number(business.value_at_risk ?? 0),
        expectedNetBenefit: Number(
          business.expected_net_benefit ??
            actionOptions.find((item) => item.action.id === bestActionId)?.expectedNetBenefit ??
            0,
        ),
        decision,
        bestAction,
        actionOptions,
      },
      segment: {
        customerId,
        segmentId,
        clusterId: segmentIdNumber,
        label: segmentLabel,
      },
    };
  }

  async getHealth(): Promise<HealthStatus> {
    try {
      const { data } = await this.http.get<HealthResponse>(
        API_ENDPOINTS.health,
      );

      return {
        status:
          data.status === 'ok' || data.status === 'healthy'
            ? 'ok'
            : 'degraded',
        mode: 'live',
        message: `API reported status "${data.status}".`,
      };
    } catch (error) {
      this.handleError(error);
    }
  }

  async getDashboard(): Promise<DashboardData> {
    await this.scoreLiveCustomers();
    const items = [...this.cache.values()];
    const actions = await this.getActions();
    return buildDashboard(items, actions);
  }

  async listCustomers(
    query: CustomerQuery,
  ): Promise<Page<IntelligenceResult>> {
    await this.scoreLiveCustomers();

    const items = [...this.cache.values()];
    return queryCustomers(items, query);
  }

  async getCustomer(customerId: string): Promise<IntelligenceResult> {
    return this.fetchIntelligence(customerId);
  }

  async getSegments(): Promise<SegmentOverview> {
    const items = [...this.cache.values()];
    return buildSegmentOverview(items);
  }

  async getInsights(): Promise<RetentionInsights> {
    const items = [...this.cache.values()];
    const actions = await this.getActions();
    return buildInsights(items, actions);
  }

  async getActions(): Promise<RetentionAction[]> {
    await this.ensureLiveCustomersAvailable();
    const firstCustomer = this.liveCustomers[0];
    if (!firstCustomer) {
      throw new NotFoundError('No live customers are available.');
    }
    const result = await this.getCustomer(firstCustomer.customerID);
    return result.business.actionOptions.map((item) => item.action);
  }

  async runWhatIf(input: WhatIfInput): Promise<WhatIfResult> {
    const result = await this.getCustomer(input.customerId);

    const action = result.business.actionOptions.find(
      (item) => item.action.id === input.actionId,
    );

    if (!action) {
      throw new ApiError(`Unknown action "${input.actionId}".`, 422);
    }

    const current = result.business;

    const currentState = {
      churnProbability: result.prediction.churnProbability,
      clv: current.clv,
      valueAtRisk: current.valueAtRisk,
      actionId: action.action.id,
      actionName: action.action.name,
      actionCost: action.action.cost,
      successRate: action.action.successRate,
      expectedNetBenefit: action.expectedNetBenefit,
      decision: current.decision,
    };

    const scenarioEnb =
      input.churnProbability *
        input.clv *
        input.successRate -
      input.actionCost;

    const scenarioDecision =
      scenarioEnb > 0 ? 'Intervene' : 'Do not intervene';

    const scenario = {
      churnProbability: input.churnProbability,
      clv: input.clv,
      valueAtRisk: input.churnProbability * input.clv,
      actionId: input.actionId,
      actionName: action.action.name,
      actionCost: input.actionCost,
      successRate: input.successRate,
      expectedNetBenefit: scenarioEnb,
      decision: scenarioDecision as 'Intervene' | 'Do not intervene',
    };

    return {
      customerId: input.customerId,
      label: 'Scenario / What-if analysis',
      current: currentState,
      scenario,
      deltaEnb: scenario.expectedNetBenefit - currentState.expectedNetBenefit,
    };
  }

  async getModelInfo(): Promise<ModelInfo> {
    try {
      const { data } = await this.http.get(API_ENDPOINTS.readiness);

      return {
        churn: {
          version: String(data.details?.model_version ?? '2.0.0'),
          artifact: 'trichurn_churn_model_v2.0.0.joblib',
          metrics: {
            rocAuc: 0.8492,
            prAuc: 0.6412,
            brierScore: 0.1355,
            logLoss: 0.4107,
            accuracy: 0.7711,
            precision: 0.5503,
            recall: 0.7429,
            f1: 0.6322,
          },
        },
        segmentation: {
          version: String(data.details?.segmentation_version ?? '5.0.0'),
          artifact: 'trichurn_segmentation_v5.0.0.joblib',
          k: Number(data.details?.segmentation_k ?? 3),
          seed: 42,
          features: [
            'tenure',
            'MonthlyCharges',
            'TotalCharges',
            'service_count',
            'contract_risk',
          ],
        },
        dataMode: 'live',
      };
    } catch (error) {
      this.handleError(error);
    }
  }
}
