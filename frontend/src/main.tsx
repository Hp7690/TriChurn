import { StrictMode } from 'react';
import { createRoot } from 'react-dom/client';
import { BrowserRouter } from 'react-router-dom';
import App from './App';
import './index.css';
import { intelligenceService } from './services';
import { AutonomyServiceProvider, autonomyService } from './services/autonomy';
import { RetentionServiceProvider, retentionService } from './services/retention';
import { ServiceProvider } from './services/ServiceContext';

const container = document.getElementById('root');
if (!container) throw new Error('Root element #root not found');

createRoot(container).render(
  <StrictMode>
    <BrowserRouter>
      <ServiceProvider service={intelligenceService}>
        <RetentionServiceProvider service={retentionService}>
          <AutonomyServiceProvider service={autonomyService}>
            <App />
          </AutonomyServiceProvider>
        </RetentionServiceProvider>
      </ServiceProvider>
    </BrowserRouter>
  </StrictMode>,
);
