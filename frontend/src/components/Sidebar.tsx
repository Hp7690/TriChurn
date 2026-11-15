import { NavLink } from 'react-router-dom';
import { useService } from '../services/ServiceContext';
import { cn } from '../utils/cn';
import { NAV_GROUPS } from './navConfig';

/** TriChurn mark: three rising bars in the Low / Medium / High risk colours. */
export function BrandMark({ className }: { className?: string }) {
  return (
    <svg viewBox="0 0 32 32" className={cn('h-8 w-8', className)} aria-hidden="true">
      <rect width="32" height="32" rx="9" className="fill-slate-900" />
      <rect x="7" y="16" width="4.5" height="9" rx="1.6" className="fill-emerald-400" />
      <rect x="13.75" y="11" width="4.5" height="14" rx="1.6" className="fill-amber-400" />
      <rect x="20.5" y="6" width="4.5" height="19" rx="1.6" className="fill-rose-400" />
    </svg>
  );
}

export function Sidebar({ onNavigate }: { onNavigate?: () => void }) {
  const service = useService();
  return (
    <div className="flex h-full w-full flex-col border-r border-slate-200 bg-surface">
      <div className="px-5 pb-4 pt-5">
        <div className="flex items-center gap-2.5">
          <BrandMark />
          <span className="text-lg font-semibold tracking-tight text-slate-900">TriChurn</span>
        </div>
        <p className="mt-2.5 text-[11px] leading-4 text-slate-500">Predict · Explain · Quantify · Decide · Retain</p>
      </div>
      <nav aria-label="Primary" className="scrollbar-thin min-h-0 flex-1 space-y-5 overflow-y-auto px-3 pb-4">
        {NAV_GROUPS.map((group) => (
          <div key={group.label} role="group" aria-label={group.label}>
            <p className="mb-1 px-3 text-xs font-semibold text-slate-500" aria-hidden="true">
              {group.label}
            </p>
            <ul className="space-y-0.5">
              {group.items.map(({ to, label, icon: Icon }) => (
                <li key={to}>
                  <NavLink
                    to={to}
                    onClick={onNavigate}
                    className={({ isActive }) =>
                      cn(
                        'group relative flex items-center gap-3 rounded-lg px-3 py-2 text-sm font-medium transition-colors',
                        isActive
                          ? 'bg-brand-50 text-brand-700'
                          : 'text-slate-600 hover:bg-slate-100 hover:text-slate-900',
                      )
                    }
                  >
                    {({ isActive }) => (
                      <>
                        <span
                          aria-hidden="true"
                          className={cn(
                            'absolute -left-3 top-1/2 h-5 w-[3px] -translate-y-1/2 rounded-r-full bg-brand-600 transition-opacity',
                            isActive ? 'opacity-100' : 'opacity-0',
                          )}
                        />
                        <Icon
                          className={cn('h-[18px] w-[18px] shrink-0', isActive ? 'text-brand-600' : 'text-slate-400 group-hover:text-slate-600')}
                          aria-hidden="true"
                        />
                        {label}
                      </>
                    )}
                  </NavLink>
                </li>
              ))}
            </ul>
          </div>
        ))}
      </nav>
      <div className="m-3 rounded-xl border border-slate-200 bg-sunken px-3 py-2.5 text-xs">
        <p className="flex items-center gap-2 font-semibold text-slate-800">
          <span
            aria-hidden="true"
            className={cn('h-2 w-2 rounded-full', service.mode === 'mock' ? 'bg-amber-500' : 'bg-emerald-500')}
          />
          {service.mode === 'mock' ? 'Demo data' : 'Live API'}
        </p>
        <p className="mt-0.5 truncate text-slate-500">{service.providerName}</p>
      </div>
    </div>
  );
}
