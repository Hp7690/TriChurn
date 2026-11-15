import type { ReactNode } from 'react';
import type { AsyncState } from '../hooks/useAsync';
import { EmptyState } from './EmptyState';
import { ErrorState } from './ErrorState';
import { LoadingSkeleton } from './LoadingSkeleton';

interface AsyncBoundaryProps<T> {
  state: AsyncState<T>;
  children: (data: T) => ReactNode;
  skeleton?: ReactNode;
  isEmpty?: (data: T) => boolean;
  emptyTitle?: string;
  emptyDescription?: string;
  errorTitle?: string;
}

/** Handles loading, error (with retry), empty and success for any async view. */
export function AsyncBoundary<T>({
  state,
  children,
  skeleton,
  isEmpty,
  emptyTitle = 'No data to show',
  emptyDescription,
  errorTitle,
}: AsyncBoundaryProps<T>) {
  if (state.status === 'error') {
    return <ErrorState title={errorTitle} message={state.error?.message} onRetry={state.reload} />;
  }
  if (state.data === null) {
    return <>{skeleton ?? <LoadingSkeleton variant="page" />}</>;
  }
  if (isEmpty?.(state.data)) {
    return <EmptyState title={emptyTitle} description={emptyDescription} />;
  }
  return (
    <div aria-busy={state.status === 'loading'} className={state.status === 'loading' ? 'opacity-60 transition-opacity' : undefined}>
      {children(state.data)}
    </div>
  );
}
