import { Route } from 'react-router-dom';
import { ClvPage } from './ClvPage';
import { CohortsPage } from './CohortsPage';
import { ExecutivePage } from './ExecutivePage';
import { ForecastPage } from './ForecastPage';
import { OpportunitiesPage } from './OpportunitiesPage';
import { RevenueLayout } from './RevenueLayout';
import { RiskPage } from './RiskPage';

/** Called (not rendered) inside <Routes> by App.tsx: returns one nested <Route> tree under /revenue. */
export function revenueRoutes() {
  return (
    <Route path="revenue" element={<RevenueLayout />}>
      <Route index element={<ExecutivePage />} />
      <Route path="clv" element={<ClvPage />} />
      <Route path="risk" element={<RiskPage />} />
      <Route path="opportunities" element={<OpportunitiesPage />} />
      <Route path="cohorts" element={<CohortsPage />} />
      <Route path="forecast" element={<ForecastPage />} />
    </Route>
  );
}
