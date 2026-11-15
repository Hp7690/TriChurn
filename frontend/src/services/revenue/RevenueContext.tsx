import { createContext, useContext, type ReactNode } from 'react';
import { HttpRevenueProvider } from './HttpRevenueProvider';
import type { RevenueProvider } from './RevenueProvider';

const baseUrl = ((import.meta as unknown as { env?: Record<string, string | undefined> }).env?.VITE_API_BASE_URL ?? '');

/** Default provider = the real HTTP API, so no app-level provider (and no main.tsx change) is required. */
export const revenueService: RevenueProvider = new HttpRevenueProvider({ baseUrl });
const RevenueContext = createContext<RevenueProvider>(revenueService);

export function RevenueServiceProvider({ service, children }: { service: RevenueProvider; children: ReactNode }) {
  return <RevenueContext.Provider value={service}>{children}</RevenueContext.Provider>;
}

export function useRevenue(): RevenueProvider {
  return useContext(RevenueContext);
}
