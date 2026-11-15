import type { ReactNode } from 'react';
import { cn } from '../utils/cn';

interface CardProps {
  title?: string;
  description?: string;
  actions?: ReactNode;
  className?: string;
  children: ReactNode;
}

export function Card({ title, description, actions, className, children }: CardProps) {
  return (
    <section className={cn('rounded-xl border border-slate-200 bg-surface p-5 shadow-sm sm:p-6', className)}>
      {(title || description || actions) && (
        <header className="mb-5 flex flex-wrap items-start justify-between gap-3">
          <div className="min-w-0">
            {title && <h2 className="text-[15px] font-semibold text-slate-900">{title}</h2>}
            {description && <p className="mt-1 text-sm text-slate-500">{description}</p>}
          </div>
          {actions}
        </header>
      )}
      {children}
    </section>
  );
}
