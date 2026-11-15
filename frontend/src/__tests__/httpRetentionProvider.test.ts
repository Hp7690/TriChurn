import axios from 'axios';
import { beforeEach, describe, expect, it, vi } from 'vitest';
import { ApiError, NotFoundError } from '../services/api/errors';
import { HttpRetentionProvider, toApiError } from '../services/retention/HttpRetentionProvider';

vi.mock('axios', () => {
  const instance = { get: vi.fn(), post: vi.fn() };
  return {
    default: { create: vi.fn(() => instance), isAxiosError: (e: unknown) => typeof e === 'object' && e !== null && 'isAxiosError' in e },
    __instance: instance,
  };
});

const http = (axios.create as unknown as () => { get: ReturnType<typeof vi.fn>; post: ReturnType<typeof vi.fn> })();
const axiosError = (status: number | undefined, message?: string) => ({
  isAxiosError: true,
  message: 'raw',
  response: status === undefined ? undefined : { status, data: message ? { error: { code: 'X', message } } : {} },
});

describe('HttpRetentionProvider', () => {
  beforeEach(() => {
    http.get.mockReset();
    http.post.mockReset();
  });

  it('maps priority filters to the API query parameters', async () => {
    http.get.mockResolvedValue({ data: { items: [], total: 0 } });
    const provider = new HttpRetentionProvider({ baseUrl: 'http://api' });
    await provider.getPriorities({ page: 2, pageSize: 10, search: '  ', riskBand: 'HIGH', minChurnProbability: 0.5, sortBy: 'value_at_risk', descending: true });
    expect(http.get).toHaveBeenCalledWith('/api/v1/retention/priorities', {
      params: { page: 2, page_size: 10, search: undefined, risk_band: 'HIGH', segment_id: undefined, decision: undefined, tier: undefined, min_churn_probability: 0.5, sort_by: 'value_at_risk', descending: true },
    });
  });

  it('url-encodes ids and posts snake_case bodies', async () => {
    http.get.mockResolvedValue({ data: {} });
    http.post.mockResolvedValue({ data: {} });
    const provider = new HttpRetentionProvider({ baseUrl: 'http://api' });
    await provider.getRecommendation('a/b c');
    expect(http.get).toHaveBeenCalledWith('/api/v1/retention/customers/a%2Fb%20c/recommendation', { params: undefined });
    await provider.recordOutcomes('cmp_1', [{ customerId: 'C-1', outcome: 'retained', actualCost: 5 }]);
    expect(http.post).toHaveBeenCalledWith('/api/v1/retention/campaigns/cmp_1/outcomes', {
      outcomes: [{ customer_id: 'C-1', outcome: 'retained', actual_cost: 5, actual_retained_revenue: undefined }],
    });
    await provider.simulate([{ actionId: 'discount_offer', decisionFilter: 'intervene', riskBands: [], successRateOverride: 0.3 }]);
    expect(http.post).toHaveBeenLastCalledWith('/api/v1/retention/simulate', {
      scenarios: [{ name: undefined, action_id: 'discount_offer', cost_override: undefined, success_rate_override: 0.3, decision_filter: 'intervene', risk_bands: [], top_n: undefined }],
    });
  });

  it('unwraps the campaign list', async () => {
    http.get.mockResolvedValue({ data: { campaigns: [{ campaign_id: 'cmp_1' }] } });
    expect(await new HttpRetentionProvider({ baseUrl: 'http://api' }).listCampaigns()).toEqual([{ campaign_id: 'cmp_1' }]);
  });

  it('turns the backend error envelope into typed errors with the server message', async () => {
    http.get.mockRejectedValue(axiosError(404, 'Customer not found in the scored portfolio.'));
    const provider = new HttpRetentionProvider({ baseUrl: 'http://api' });
    await expect(provider.getRecommendation('x')).rejects.toBeInstanceOf(NotFoundError);
    await expect(provider.getRecommendation('x')).rejects.toThrow('Customer not found in the scored portfolio.');
  });

  it('distinguishes a 404 without an envelope, server errors and an unreachable API', () => {
    expect(toApiError(axiosError(404))).toBeInstanceOf(NotFoundError);
    expect(toApiError(axiosError(404)).message).toMatch(/HTTP 404/);          // never the misleading "Customer was not found."
    const server = toApiError(axiosError(503, 'The capability is unavailable.'));
    expect(server).toBeInstanceOf(ApiError);
    expect((server as ApiError).status).toBe(503);
    expect(toApiError(axiosError(undefined)).message).toMatch(/could not be reached/);
    expect(toApiError(new Error('boom')).message).toBe('boom');
  });
});
