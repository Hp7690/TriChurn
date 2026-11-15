import { Outlet } from 'react-router-dom';
import { PageHeader } from '../../components/PageHeader';
import { SectionTabs } from '../../components/ui/SectionTabs';

const TABS = [
  { to: '/autonomous', label: 'Command Center', end: true },
  { to: '/autonomous/risks', label: 'Risk Monitor', end: false },
  { to: '/autonomous/recommendations', label: 'Recommendations', end: false },
  { to: '/autonomous/approvals', label: 'Approvals', end: false },
  { to: '/autonomous/learning', label: 'Learning', end: false },
  { to: '/autonomous/audit', label: 'Audit', end: false },
];

export function AutonomyLayout() {
  return (
    <>
      <PageHeader
        title="Autonomous Retention Intelligence"
        description="Rule-based, explainable recommendations with human approval. Nothing here contacts customers or any external system."
      />
      <SectionTabs label="Autonomous retention sections" tabs={TABS} />
      <Outlet />
    </>
  );
}
