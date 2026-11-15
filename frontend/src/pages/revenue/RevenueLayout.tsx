import { Outlet } from 'react-router-dom';
import { PageHeader } from '../../components/PageHeader';
import { SectionTabs } from '../../components/ui/SectionTabs';

const TABS = [
  { to: '/revenue', label: 'Executive', end: true },
  { to: '/revenue/clv', label: 'CLV', end: false },
  { to: '/revenue/risk', label: 'Revenue at Risk', end: false },
  { to: '/revenue/opportunities', label: 'Upsell & Cross-sell', end: false },
  { to: '/revenue/cohorts', label: 'Cohorts', end: false },
  { to: '/revenue/forecast', label: 'Forecasting', end: false },
];

export function RevenueLayout() {
  return (
    <>
      <PageHeader
        title="Customer Value & Revenue Intelligence"
        description="Revenue, not profit. Every figure carries an evidence status; unavailable values are shown as unavailable, never as zero. Nothing here contacts customers or executes offers."
      />
      <SectionTabs label="Revenue intelligence sections" tabs={TABS} />
      <Outlet />
    </>
  );
}
