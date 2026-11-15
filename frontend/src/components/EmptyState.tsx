import { Inbox } from 'lucide-react';
import type { ReactNode } from 'react';

interface EmptyStateProps {
  title: string;
  description?: string;
  action?: ReactNode;
}

export function EmptyState({ title, description, action }: EmptyStateProps) {
  return (
    <div className="flex flex-col items-center justify-center rounded-xl border border-dashed border-slate-300 bg-sunken px-6 py-14 text-center">
      <span className="grid h-11 w-11 place-items-center rounded-full bg-slate-100 text-slate-500" aria-hidden="true">
        <Inbox className="h-5 w-5" />
      </span>
      <h2 className="mt-4 text-base font-semibold text-slate-900">{title}</h2>
      {description && <p className="mt-1 max-w-md text-sm leading-6 text-slate-600">{description}</p>}
      {action && <div className="mt-5">{action}</div>}
    </div>
  );
}
