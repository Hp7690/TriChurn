import { render } from '@testing-library/react';
import { MemoryRouter } from 'react-router-dom';
import { AppRoutes } from '../App';
import { MockDataProvider, type MockProviderOptions } from '../services/adapters/MockDataProvider';
import { IntelligenceService } from '../services/IntelligenceService';
import { ServiceProvider } from '../services/ServiceContext';

export function createTestService(options: MockProviderOptions = {}): IntelligenceService {
  return new IntelligenceService(new MockDataProvider({ latencyMs: 0, ...options }));
}

export function renderApp(route: string, service: IntelligenceService = createTestService()) {
  const view = render(
    <MemoryRouter initialEntries={[route]}>
      <ServiceProvider service={service}>
        <AppRoutes />
      </ServiceProvider>
    </MemoryRouter>,
  );
  return { service, ...view };
}
