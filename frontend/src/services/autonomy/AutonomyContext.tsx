import { createContext, useContext, type ReactNode } from 'react';
import type { AutonomyProvider } from './AutonomyProvider';

const AutonomyContext = createContext<AutonomyProvider | null>(null);

export function AutonomyServiceProvider({ service, children }: { service: AutonomyProvider; children: ReactNode }) {
  return <AutonomyContext.Provider value={service}>{children}</AutonomyContext.Provider>;
}

export function useAutonomy(): AutonomyProvider {
  const service = useContext(AutonomyContext);
  if (!service) throw new Error('useAutonomy must be used inside <AutonomyServiceProvider>.');
  return service;
}
