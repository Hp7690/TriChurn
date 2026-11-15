import { HttpRetentionProvider } from './HttpRetentionProvider';
import type { RetentionProvider } from './RetentionProvider';

/**
 * Retention Intelligence always talks to the real Phase 9 API (there is deliberately no mock mode: demo campaign
 * results would be fabricated history). Set VITE_API_BASE_URL (default http://localhost:8000).
 */
export function createRetentionProvider(): RetentionProvider {
  return new HttpRetentionProvider({ baseUrl: import.meta.env.VITE_API_BASE_URL ?? 'http://localhost:8000' });
}

export const retentionService: RetentionProvider = createRetentionProvider();

export type { RetentionProvider } from './RetentionProvider';
export { HttpRetentionProvider, toApiError } from './HttpRetentionProvider';
export { RetentionServiceProvider, useRetention } from './RetentionContext';
