import { cn } from '../utils/cn';

type Variant = 'card' | 'table' | 'chart' | 'page';

function Block({ className }: { className?: string }) {
  return <div className={cn('rounded-xl bg-slate-200/70 motion-safe:animate-pulse', className)} />;
}

export function LoadingSkeleton({ variant = 'card', rows = 5 }: { variant?: Variant; rows?: number }) {
  let body;
  if (variant === 'table') {
    body = (
      <div className="space-y-2">
        <Block className="h-9" />
        {Array.from({ length: rows }, (_, i) => (
          <Block key={i} className="h-10" />
        ))}
      </div>
    );
  } else if (variant === 'chart') {
    body = <Block className="h-64" />;
  } else if (variant === 'page') {
    body = (
      <div className="space-y-6">
        <div className="grid gap-4 sm:grid-cols-2 lg:grid-cols-3">
          {Array.from({ length: 6 }, (_, i) => (
            <Block key={i} className="h-28" />
          ))}
        </div>
        <div className="grid gap-4 lg:grid-cols-2">
          <Block className="h-72" />
          <Block className="h-72" />
        </div>
      </div>
    );
  } else {
    body = <Block className="h-28" />;
  }
  return (
    <div role="status" aria-live="polite" aria-label="Loading">
      <span className="sr-only">Loading…</span>
      {body}
    </div>
  );
}
