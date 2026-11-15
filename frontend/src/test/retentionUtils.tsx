import { render } from '@testing-library/react';
import { MemoryRouter } from 'react-router-dom';
import { AppRoutes } from '../App';
import { RetentionServiceProvider } from '../services/retention/RetentionContext';
import { ServiceProvider } from '../services/ServiceContext';
import { FakeRetentionProvider } from './fakeRetention';
import { createTestService } from './utils';

export function renderRetention(route: string, provider: FakeRetentionProvider = new FakeRetentionProvider()) {
  const view = render(
    <MemoryRouter initialEntries={[route]}>
      <ServiceProvider service={createTestService()}>
        <RetentionServiceProvider service={provider}>
          <AppRoutes />
        </RetentionServiceProvider>
      </ServiceProvider>
    </MemoryRouter>,
  );
  return { provider, ...view };
}
