import { NavLink } from 'react-router-dom';
import { cn } from '../../utils/cn';

export interface SectionTab {
  to: string;
  label: string;
  end?: boolean;
}

/** Route-backed tab bar used by Retention, Autonomous and Revenue. */
export function SectionTabs({ label, tabs }: { label: string; tabs: readonly SectionTab[] }) {
  return (
    <nav aria-label={label} className="scrollbar-thin mb-6 flex gap-1 overflow-x-auto border-b border-slate-200">
      {tabs.map((tab) => (
        <NavLink
          key={tab.to}
          to={tab.to}
          end={tab.end}
          className={({ isActive }) =>
            cn(
              '-mb-px whitespace-nowrap border-b-2 px-4 py-2.5 text-sm font-medium transition-colors',
              isActive
                ? 'border-brand-600 text-brand-700'
                : 'border-transparent text-slate-600 hover:border-slate-300 hover:text-slate-900',
            )
          }
        >
          {tab.label}
        </NavLink>
      ))}
    </nav>
  );
}
