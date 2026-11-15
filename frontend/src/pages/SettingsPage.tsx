import { Monitor, Moon, Sun, type LucideIcon } from 'lucide-react';
import { useState } from 'react';
import { Card } from '../components/Card';
import { PageHeader } from '../components/PageHeader';
import { useService } from '../services/ServiceContext';
import { useTheme, type ThemePreference } from '../theme/themeStore';
import { cn } from '../utils/cn';

const THEME_OPTIONS: Array<{ value: ThemePreference; label: string; icon: LucideIcon }> = [
  { value: 'light', label: 'Light', icon: Sun },
  { value: 'dark', label: 'Dark', icon: Moon },
  { value: 'system', label: 'System', icon: Monitor },
];

function AppearanceCard() {
  const { preference, setPreference } = useTheme();
  return (
    <Card title="Appearance" description="Applies to this browser only. System follows your operating-system setting.">
      <div role="radiogroup" aria-label="Theme" className="inline-flex rounded-lg border border-slate-200 bg-sunken p-1">
        {THEME_OPTIONS.map(({ value, label, icon: Icon }) => {
          const selected = preference === value;
          return (
            <button
              key={value}
              type="button"
              role="radio"
              aria-checked={selected}
              onClick={() => setPreference(value)}
              className={cn(
                'inline-flex items-center gap-2 rounded-md px-3.5 py-1.5 text-sm font-medium transition-colors',
                selected ? 'bg-surface text-slate-900 shadow-sm' : 'text-slate-600 hover:text-slate-900',
              )}
            >
              <Icon className="h-4 w-4" aria-hidden="true" />
              {label}
            </button>
          );
        })}
      </div>
    </Card>
  );
}

export function SettingsPage() {
  const service = useService();
  const [failing, setFailing] = useState(service.isSimulatingFailure);

  const toggle = () => {
    const next = !failing;
    service.setSimulatedFailure(next);
    setFailing(next);
  };

  return (
    <>
      <PageHeader title="Settings" description="Data-source information and development controls. There is no authentication or account management." />
      <div className="space-y-6">
        <AppearanceCard />
        <Card title="Data source">
          <dl className="grid gap-4 text-sm sm:grid-cols-3">
            <div><dt className="text-xs text-slate-500">Provider</dt><dd className="mt-0.5 font-medium text-slate-900">{service.providerName}</dd></div>
            <div><dt className="text-xs text-slate-500">Mode</dt><dd className="mt-0.5 font-medium text-slate-900">{service.mode === 'mock' ? 'Demo data (mock API)' : 'Live API'}</dd></div>
            <div><dt className="text-xs text-slate-500">Switch</dt><dd className="mt-0.5 font-medium text-slate-900">VITE_DATA_PROVIDER in .env</dd></div>
          </dl>
        </Card>

        {service.canSimulateFailure && (
          <Card title="Developer: simulate API failure" description="Forces every mock call to fail so you can check error states and the Retry button.">
            <button
              type="button"
              role="switch"
              aria-checked={failing}
              onClick={toggle}
              className="inline-flex items-center gap-3 text-sm font-medium text-slate-800"
            >
              <span className={cn('relative h-6 w-11 rounded-full transition-colors', failing ? 'bg-rose-600' : 'bg-slate-300')}>
                <span className={cn('absolute top-0.5 h-5 w-5 rounded-full bg-white shadow transition-all', failing ? 'left-[22px]' : 'left-0.5')} />
              </span>
              Simulate API failure: {failing ? 'On' : 'Off'}
            </button>
          </Card>
        )}
      </div>
    </>
  );
}
