import { createContext, useContext, type ReactNode } from 'react';
import type { RetentionProvider } from './RetentionProvider';

const RetentionContext = createContext<RetentionProvider | null>(null);

export function RetentionServiceProvider({ service, children }: { service: RetentionProvider; children: ReactNode }) {
  return <RetentionContext.Provider value={service}>{children}</RetentionContext.Provider>;
}

export function useRetention(): RetentionProvider {
  const service = useContext(RetentionContext);
  if (!service) throw new Error('useRetention must be used inside <RetentionServiceProvider>.');
  return service;
}
