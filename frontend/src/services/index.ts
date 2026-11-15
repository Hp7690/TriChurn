import type { DataProvider } from './api/DataProvider';
import { FastAPIDataProvider } from './adapters/FastAPIDataProvider';
import { MockDataProvider } from './adapters/MockDataProvider';
import { IntelligenceService } from './IntelligenceService';

/**
 * ┌──────────────────────────────────────────────────────────────────────┐
 * │  THE DATA-SOURCE SWITCH                                              │
 * │                                                                      │
 * │  This is the ONLY place that decides which provider the app uses.    │
 * │    VITE_DATA_PROVIDER=mock     → MockDataProvider    (default)       │
 * │    VITE_DATA_PROVIDER=fastapi  → FastAPIDataProvider (Phase 6 API)  │
 * │  No page or component imports a provider or mock data directly.      │
 * └──────────────────────────────────────────────────────────────────────┘
 */
export function createDataProvider(): DataProvider {
  const env = import.meta.env;
  if (env.VITE_DATA_PROVIDER === 'fastapi') {
    return new FastAPIDataProvider({ baseUrl: env.VITE_API_BASE_URL ?? 'http://localhost:8000' });
  }
  const latency = Number(env.VITE_MOCK_LATENCY_MS ?? 250);
  return new MockDataProvider({
    latencyMs: Number.isFinite(latency) ? latency : 250,
    failureMode: env.VITE_MOCK_FAIL === 'always' ? 'always' : 'none',
  });
}

export const intelligenceService = new IntelligenceService(createDataProvider());

export { IntelligenceService } from './IntelligenceService';
export type { DataProvider } from './api/DataProvider';
export { MockDataProvider } from './adapters/MockDataProvider';
export { FastAPIDataProvider } from './adapters/FastAPIDataProvider';
export { ApiError, NotFoundError, ProviderNotReadyError } from './api/errors';
