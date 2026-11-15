import { Activity, Route as RouteIcon, type LucideIcon } from 'lucide-react';

/** Phase 13 sidebar entries. Spread into the existing NAV array (see PHASE13_INTEGRATION_GUIDE.md). */
export const EXPERIENCE_NAV: Array<{ to: string; label: string; icon: LucideIcon }> = [
  { to: '/experience', label: 'Experience', icon: Activity },
  { to: '/experience-lifecycle', label: 'Lifecycle', icon: RouteIcon },
];
