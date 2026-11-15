import { HttpAutonomyProvider } from './HttpAutonomyProvider';
import type { AutonomyProvider } from './AutonomyProvider';

/** Always the real Phase 11 API: a mock mode would fabricate recommendations, approvals and outcomes. */
export function createAutonomyProvider(): AutonomyProvider {
  return new HttpAutonomyProvider({ baseUrl: import.meta.env.VITE_API_BASE_URL ?? 'http://localhost:8000' });
}

export const autonomyService: AutonomyProvider = createAutonomyProvider();

export type { AutonomyProvider } from './AutonomyProvider';
export { HttpAutonomyProvider, newIdempotencyKey } from './HttpAutonomyProvider';
export { AutonomyServiceProvider, useAutonomy } from './AutonomyContext';
