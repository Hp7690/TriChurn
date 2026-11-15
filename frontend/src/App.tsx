import { Navigate, Route, Routes } from 'react-router-dom';
import { ErrorBoundary } from './components/ErrorBoundary';
import { AppLayout } from './layouts/AppLayout';
import { CustomerDetailPage } from './pages/CustomerDetailPage';
import { CustomersPage } from './pages/CustomersPage';
import { DashboardPage } from './pages/DashboardPage';
import { ExperiencePage } from './pages/ExperiencePage';
import { InsightsPage } from './pages/InsightsPage';
import { LifecyclePage } from './pages/LifecyclePage';
import { ModelPage } from './pages/ModelPage';
import { NotFoundPage } from './pages/NotFoundPage';
import { SegmentsPage } from './pages/SegmentsPage';
import { SettingsPage } from './pages/SettingsPage';
import { WhatIfPage } from './pages/WhatIfPage';
import { ApprovalCenterPage } from './pages/autonomy/ApprovalCenterPage';
import { AuditPage } from './pages/autonomy/AuditPage';
import { AutonomyLayout } from './pages/autonomy/AutonomyLayout';
import { CommandCenterPage } from './pages/autonomy/CommandCenterPage';
import { LearningPage } from './pages/autonomy/LearningPage';
import { RecommendationsPage } from './pages/autonomy/RecommendationsPage';
import { RiskMonitorPage } from './pages/autonomy/RiskMonitorPage';
import { RetentionCampaignsPage } from './pages/retention/RetentionCampaignsPage';
import { RetentionLayout } from './pages/retention/RetentionLayout';
import { RetentionOverviewPage } from './pages/retention/RetentionOverviewPage';
import { RetentionPrioritiesPage } from './pages/retention/RetentionPrioritiesPage';
import { RetentionRecommendationPage } from './pages/retention/RetentionRecommendationPage';
import { RetentionSimulatorPage } from './pages/retention/RetentionSimulatorPage';

import { revenueRoutes } from './pages/revenue/revenueRoutes'; // PHASE12
export function AppRoutes() {
  return (
    <Routes>
      <Route element={<AppLayout />}>
        <Route index element={<Navigate to="/dashboard" replace />} />
        <Route path="dashboard" element={<DashboardPage />} />
        <Route path="customers" element={<CustomersPage />} />
        <Route path="customers/:customerId" element={<CustomerDetailPage />} />
        <Route path="segments" element={<SegmentsPage />} />
        <Route path="insights" element={<InsightsPage />} />
        <Route path="what-if" element={<WhatIfPage />} />
        <Route path="autonomous" element={<AutonomyLayout />}>
          <Route index element={<CommandCenterPage />} />
          <Route path="risks" element={<RiskMonitorPage />} />
          <Route path="recommendations" element={<RecommendationsPage />} />
          <Route path="approvals" element={<ApprovalCenterPage />} />
          <Route path="learning" element={<LearningPage />} />
          <Route path="audit" element={<AuditPage />} />
        </Route>
        <Route path="retention" element={<RetentionLayout />}>
          <Route index element={<RetentionOverviewPage />} />
          <Route path="priorities" element={<RetentionPrioritiesPage />} />
          <Route path="recommendations" element={<RetentionRecommendationPage />} />
          <Route path="recommendations/:customerId" element={<RetentionRecommendationPage />} />
          <Route path="simulator" element={<RetentionSimulatorPage />} />
          <Route path="campaigns" element={<RetentionCampaignsPage />} />
        </Route>
        {revenueRoutes()} {/* PHASE12 */}
        <Route path="model" element={<ModelPage />} />
        <Route path="settings" element={<SettingsPage />} />
        <Route path="experience" element={<ExperiencePage />} />
        <Route path="experience-lifecycle" element={<LifecyclePage />} />
        <Route path="*" element={<NotFoundPage />} />
      </Route>
    </Routes>
  );
}

export default function App() {
  return (
    <ErrorBoundary title="TriChurn hit an unexpected error.">
      <AppRoutes />
    </ErrorBoundary>
  );
}
