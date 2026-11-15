import type { AvailabilityResponse, LifecycleResponse } from '../types/experience';
import { ApiError } from './api/errors';
import { EXPERIENCE_ENDPOINTS } from './api/experienceContract';

/** What the Experience pages need. Pages take this as a prop so tests can supply a fake. */
export interface ExperienceApi {
  readonly baseUrl: string;
  getAvailability(): Promise<AvailabilityResponse>;
  getLifecycle(): Promise<LifecycleResponse>;
}

export interface ExperienceClientOptions {
  baseUrl?: string;
  fetchImpl?: typeof fetch;
}

function defaultBaseUrl(): string {
  return (import.meta.env.VITE_API_BASE_URL ?? 'http://localhost:8000').replace(/\/+$/, '');
}

/**
 * Reads the Phase 13 backend directly. It is independent of VITE_DATA_PROVIDER on purpose: experience figures are
 * never produced by the mock provider, so if the backend is unreachable the pages show an error, not sample numbers.
 */
export function createExperienceApi(options: ExperienceClientOptions = {}): ExperienceApi {
  const baseUrl = (options.baseUrl ?? defaultBaseUrl()).replace(/\/+$/, '');

  async function get<T>(path: string): Promise<T> {
    const doFetch = options.fetchImpl ?? fetch;
    let response: Response;
    try {
      response = await doFetch(`${baseUrl}${path}`, { headers: { Accept: 'application/json' } });
    } catch {
      throw new ApiError(`The experience API at ${baseUrl} could not be reached.`);
    }
    if (!response.ok) {
      let message = `The experience API returned an error (${response.status}).`;
      try {
        const body = (await response.json()) as { error?: { message?: string } };
        if (body.error?.message) message = body.error.message;
      } catch {
        /* keep the generic message */
      }
      throw new ApiError(message, response.status);
    }
    return (await response.json()) as T;
  }

  return {
    baseUrl,
    getAvailability: () => get<AvailabilityResponse>(EXPERIENCE_ENDPOINTS.availability),
    getLifecycle: () => get<LifecycleResponse>(EXPERIENCE_ENDPOINTS.lifecycle),
  };
}

export const experienceApi: ExperienceApi = createExperienceApi();
