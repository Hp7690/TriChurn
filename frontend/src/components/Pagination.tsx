import { ChevronLeft, ChevronRight } from 'lucide-react';

interface PaginationProps {
  page: number;
  pageCount: number;
  total: number;
  pageSize: number;
  onPageChange: (page: number) => void;
}

export function Pagination({ page, pageCount, total, pageSize, onPageChange }: PaginationProps) {
  const from = total === 0 ? 0 : (page - 1) * pageSize + 1;
  const to = Math.min(total, page * pageSize);
  const btn =
    'btn btn-secondary btn-sm';
  return (
    <nav aria-label="Pagination" className="flex flex-wrap items-center justify-between gap-3 pt-4">
      <p className="text-sm text-slate-600">
        Showing {from}–{to} of {total}
      </p>
      <div className="flex items-center gap-2">
        <button type="button" className={btn} disabled={page <= 1} onClick={() => onPageChange(page - 1)}>
          <ChevronLeft className="h-4 w-4" aria-hidden="true" /> Previous
        </button>
        <span className="text-sm text-slate-600">
          Page {page} of {pageCount}
        </span>
        <button type="button" className={btn} disabled={page >= pageCount} onClick={() => onPageChange(page + 1)}>
          Next <ChevronRight className="h-4 w-4" aria-hidden="true" />
        </button>
      </div>
    </nav>
  );
}
