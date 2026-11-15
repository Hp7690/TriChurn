import type { ReactNode } from 'react';
import { EmptyState } from '../components/EmptyState';
import { ErrorBoundary } from '../components/ErrorBoundary';

interface ChartFrameProps {
  /** Plain-language description of the chart, read by assistive technology. */
  description: string;
  isEmpty?: boolean;
  height?: number;
  children: ReactNode;
}

function ChartFallback() {
  return (
    <div role="alert" className="grid h-full place-items-center rounded-lg bg-sunken p-4 text-center text-sm text-slate-600">
      This chart is unavailable right now. The underlying figures are still shown elsewhere on this page.
    </div>
  );
}

/** Gives every chart a fixed-height container, an accessible label, an empty state and an error fallback. */
export function ChartFrame({ description, isEmpty = false, height = 260, children }: ChartFrameProps) {
  if (isEmpty) return <EmptyState title="No chart data" description="There is nothing to plot yet." />;
  return (
    <div style={{ height }} role="img" aria-label={description} className="w-full min-w-0">
      <ErrorBoundary fallback={<ChartFallback />}>{children}</ErrorBoundary>
    </div>
  );
}
