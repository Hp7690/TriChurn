import { Bot, Cpu, LayoutDashboard, Lightbulb, PieChart, Settings, SlidersHorizontal, Target, TrendingUp, Users, type LucideIcon } from 'lucide-react';
import { EXPERIENCE_NAV } from './experienceNav';

export interface NavItem {
  to: string;
  label: string;
  icon: LucideIcon;
}

export interface NavGroup {
  label: string;
  items: NavItem[];
}

/**
 * Sidebar groups. Reading the groups top to bottom yields exactly the original
 * flat order (Dashboard ... Settings); only the grouping is new, so every route
 * and its position are preserved.
 */
export const NAV_GROUPS: NavGroup[] = [
  {
    label: 'Analyze',
    items: [
      { to: '/dashboard', label: 'Dashboard', icon: LayoutDashboard },
      { to: '/customers', label: 'Customers', icon: Users },
      { to: '/segments', label: 'Segments', icon: PieChart },
      { to: '/insights', label: 'Insights', icon: Lightbulb },
    ],
  },
  {
    label: 'Act',
    items: [
      { to: '/what-if', label: 'What-if', icon: SlidersHorizontal },
      { to: '/retention', label: 'Retention', icon: Target },
      { to: '/autonomous', label: 'Autonomous', icon: Bot },
      { to: '/revenue', label: 'Revenue', icon: TrendingUp },
    ],
  },
  {
    label: 'Evaluate',
    items: [{ to: '/model', label: 'Model', icon: Cpu }, ...EXPERIENCE_NAV],
  },
  {
    label: 'Workspace',
    items: [{ to: '/settings', label: 'Settings', icon: Settings }],
  },
];

/** Labels for the breadcrumb trail, keyed by the path segment. */
export const SEGMENT_LABELS: Record<string, string> = {
  dashboard: 'Dashboard',
  customers: 'Customers',
  segments: 'Segments',
  insights: 'Insights',
  'what-if': 'What-if analysis',
  retention: 'Retention',
  autonomous: 'Autonomous',
  revenue: 'Revenue',
  model: 'Model',
  experience: 'Experience',
  'experience-lifecycle': 'Lifecycle',
  settings: 'Settings',
};

/** Second-level labels, keyed by `<parent>/<segment>`. */
export const SUB_SEGMENT_LABELS: Record<string, string> = {
  'retention/priorities': 'Priorities',
  'retention/recommendations': 'Recommendations',
  'retention/simulator': 'Simulator',
  'retention/campaigns': 'Campaigns',
  'autonomous/risks': 'Risk Monitor',
  'autonomous/recommendations': 'Recommendations',
  'autonomous/approvals': 'Approvals',
  'autonomous/learning': 'Learning',
  'autonomous/audit': 'Audit',
  'revenue/clv': 'CLV',
  'revenue/risk': 'Revenue at Risk',
  'revenue/opportunities': 'Upsell & Cross-sell',
  'revenue/cohorts': 'Cohorts',
  'revenue/forecast': 'Forecasting',
};

/** Third-level detail pages (an id in the URL). */
export const DETAIL_LABELS: Record<string, string> = {
  customers: 'Customer details',
  'retention/recommendations': 'Recommendation',
};

export function groupLabelFor(pathname: string): string | null {
  const first = `/${pathname.split('/').filter(Boolean)[0] ?? ''}`;
  const group = NAV_GROUPS.find((g) => g.items.some((item) => item.to === first));
  return group?.label ?? null;
}
