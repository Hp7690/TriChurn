import { createContext, useContext, type ReactNode } from 'react';
import type { IntelligenceService } from './IntelligenceService';

const ServiceContext = createContext<IntelligenceService | null>(null);

export function ServiceProvider({ service, children }: { service: IntelligenceService; children: ReactNode }) {
  return <ServiceContext.Provider value={service}>{children}</ServiceContext.Provider>;
}

export function useService(): IntelligenceService {
  const service = useContext(ServiceContext);
  if (!service) throw new Error('useService must be used inside <ServiceProvider>.');
  return service;
}
