export class ApiError extends Error {
  readonly status?: number;

  constructor(message: string, status?: number) {
    super(message);
    this.name = 'ApiError';
    this.status = status;
  }
}

export class NotFoundError extends ApiError {
  constructor(message = 'Resource not found.') {
    super(message, 404);
    this.name = 'NotFoundError';
  }
}

/** Thrown by adapters that exist as a contract but are not wired to a backend yet. */
export class ProviderNotReadyError extends ApiError {
  constructor(operation: string) {
    super(`${operation} is not available yet: the Phase 6 FastAPI adapter is not connected.`, 501);
    this.name = 'ProviderNotReadyError';
  }
}

export function toError(value: unknown): Error {
  if (value instanceof Error) return value;
  return new Error(typeof value === 'string' ? value : 'Unknown error');
}
