/**
 * TriChurn — Phase 6 FastAPI API contract.
 *
 * These endpoints match the verified Phase 6 backend.
 */
export const API_ENDPOINTS = {
  health: '/api/v1/health',
  readiness: '/api/v1/readiness',
  liveness: '/api/v1/liveness',
  predict: '/api/v1/predict',
  explain: '/api/v1/explain',
  business: '/api/v1/business',
  segment: '/api/v1/segment',
  intelligence: '/api/v1/customer-intelligence',
} as const;

export type ApiEndpointName = keyof typeof API_ENDPOINTS;

export interface HealthResponse {
  status: string;
  service?: string;
  api_version?: string;
  app_version?: string;
  environment?: string;
  [key: string]: unknown;
}
export { EXPERIENCE_ENDPOINTS } from './experienceContract';
