import { Outlet } from 'react-router-dom';
import { PageHeader } from '../../components/PageHeader';
import { SectionTabs } from '../../components/ui/SectionTabs';

const TABS = [
  { to: '/retention', label: 'Overview', end: true },
  { to: '/retention/priorities', label: 'Priorities', end: false },
  { to: '/retention/recommendations', label: 'Recommendations', end: false },
  { to: '/retention/simulator', label: 'Simulator', end: false },
  { to: '/retention/campaigns', label: 'Campaigns', end: false },
];

export function RetentionLayout() {
  return (
    <>
      <PageHeader
        title="Retention Intelligence"
        description="Prioritise customers, choose retention actions, simulate campaign economics and track real campaign results."
      />
      <p className="mb-4 rounded-lg border border-amber-200 bg-amber-50 px-4 py-2.5 text-sm text-amber-900" role="note">
        Figures marked <strong>ESTIMATE</strong> use assumed action costs and success rates from the Phase 4 configuration.
        They are not measured results, and nothing here claims causal uplift.
      </p>
      <SectionTabs label="Retention sections" tabs={TABS} />
      <Outlet />
    </>
  );
}
