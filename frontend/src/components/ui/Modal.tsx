import { X } from 'lucide-react';
import { useRef, type ReactNode } from 'react';
import { useDialog } from './useDialog';

interface ModalProps {
  open: boolean;
  onClose: () => void;
  title: string;
  description?: string;
  /** Right-aligned action buttons (use <Button>). */
  footer?: ReactNode;
  children?: ReactNode;
}

/** Centered dialog for short, focused tasks. Use <Drawer> for longer forms. */
export function Modal({ open, onClose, title, description, footer, children }: ModalProps) {
  const panelRef = useRef<HTMLDivElement>(null);
  useDialog(open, onClose, panelRef);
  if (!open) return null;
  return (
    <div className="fixed inset-0 z-50 grid place-items-center p-4">
      <div className="absolute inset-0 bg-overlay/60 backdrop-blur-[2px]" onClick={onClose} aria-hidden="true" />
      <div
        ref={panelRef}
        role="dialog"
        aria-modal="true"
        aria-label={title}
        className="relative w-full max-w-md rounded-2xl border border-slate-200 bg-surface shadow-xl motion-safe:animate-pop-in"
      >
        <div className="flex items-start justify-between gap-4 px-6 pt-5">
          <div>
            <h2 className="text-base font-semibold text-slate-900">{title}</h2>
            {description && <p className="mt-1 text-sm text-slate-600">{description}</p>}
          </div>
          <button
            type="button"
            onClick={onClose}
            aria-label="Close"
            className="-mr-2 grid h-8 w-8 shrink-0 place-items-center rounded-lg text-slate-500 hover:bg-slate-100 hover:text-slate-900"
          >
            <X className="h-5 w-5" aria-hidden="true" />
          </button>
        </div>
        {children && <div className="px-6 py-4 text-sm text-slate-700">{children}</div>}
        {footer && <div className="flex justify-end gap-2 border-t border-slate-200 px-6 py-4">{footer}</div>}
      </div>
    </div>
  );
}
