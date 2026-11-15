/// <reference types="vite/client" />

interface ImportMetaEnv {
  readonly VITE_DATA_PROVIDER?: 'mock' | 'fastapi';
  readonly VITE_API_BASE_URL?: string;
  readonly VITE_MOCK_LATENCY_MS?: string;
  readonly VITE_MOCK_FAIL?: string;
}
