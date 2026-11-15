import { FlaskConical } from 'lucide-react';
import { useService } from '../services/ServiceContext';

export function DataModeBanner() {
  const service = useService();
  if (service.mode !== 'mock') return null;
  return (
    <div role="status" className="flex items-center justify-center gap-2 border-b border-amber-200 bg-amber-50 px-4 py-1.5 text-center text-xs font-medium text-amber-900">
      <FlaskConical className="h-4 w-4 shrink-0" aria-hidden="true" />
      <span>
        DEMO DATA · MOCK API — deterministic sample data; no FastAPI backend is connected.
      </span>
    </div>
  );
}
