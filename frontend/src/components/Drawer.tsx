import { X } from 'lucide-react';
import { useRef, type ReactNode } from 'react';
import { cn } from '../utils/cn';
import { useDialog } from './ui/useDialog';

interface DrawerProps {
  open: boolean;
  onClose: () => void;
  title: string;
  side?: 'left' | 'right';
  /** Skip the title bar and padding: the children supply their own chrome (used for navigation). */
  bare?: boolean;
  children: ReactNode;
}

export function Drawer({ open, onClose, title, side = 'right', bare = false, children }: DrawerProps) {
  const panelRef = useRef<HTMLDivElement>(null);
  const closeRef = useRef<HTMLButtonElement>(null);
  useDialog(open, onClose, panelRef, bare ? undefined : closeRef);

  if (!open) return null;
  return (
    <div className="fixed inset-0 z-50">
      <div className="absolute inset-0 bg-overlay/60 backdrop-blur-[2px]" onClick={onClose} aria-hidden="true" />
      <div
        ref={panelRef}
        role="dialog"
        aria-modal="true"
        aria-label={title}
        className={cn(
          'absolute inset-y-0 flex max-w-[88vw] flex-col bg-surface text-slate-900 shadow-xl',
          bare ? 'w-72' : 'w-[26rem]',
          side === 'left' ? 'left-0 motion-safe:animate-slide-in' : 'right-0 border-l border-slate-200 motion-safe:animate-slide-in-right',
        )}
      >
        {!bare && (
          <div className="flex h-14 shrink-0 items-center justify-between border-b border-slate-200 px-5">
            <span className="text-sm font-semibold">{title}</span>
            <button
              ref={closeRef}
              type="button"
              onClick={onClose}
              aria-label="Close"
              className="grid h-8 w-8 place-items-center rounded-lg text-slate-500 hover:bg-slate-100 hover:text-slate-900"
            >
              <X className="h-5 w-5" aria-hidden="true" />
            </button>
          </div>
        )}
        <div className="min-h-0 flex-1 overflow-y-auto">{children}</div>
      </div>
    </div>
  );
}
