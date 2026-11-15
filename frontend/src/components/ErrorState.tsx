import { AlertTriangle, RefreshCw } from 'lucide-react';

interface ErrorStateProps {
  title?: string;
  message?: string;
  onRetry?: () => void;
}

export function ErrorState({ title = 'Unable to load customer intelligence.', message, onRetry }: ErrorStateProps) {
  return (
    <div role="alert" className="flex flex-col items-center rounded-xl border border-rose-200 bg-rose-50 px-6 py-12 text-center">
      <span className="grid h-11 w-11 place-items-center rounded-full bg-rose-100 text-rose-600" aria-hidden="true">
        <AlertTriangle className="h-5 w-5" />
      </span>
      <p className="mt-4 text-base font-semibold text-rose-900">{title}</p>
      {message && <p className="mt-1 max-w-md text-sm leading-6 text-rose-800">{message}</p>}
      {onRetry && (
        <button type="button" onClick={onRetry} className="btn btn-danger mt-5">
          <RefreshCw className="h-4 w-4" aria-hidden="true" />
          Retry
        </button>
      )}
    </div>
  );
}
