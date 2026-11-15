import { Menu, Search, User } from 'lucide-react';
import { useState, type FormEvent } from 'react';
import { useNavigate } from 'react-router-dom';
import { BrandMark } from './Sidebar';
import { Breadcrumbs } from './Breadcrumbs';
import { ThemeToggle } from './ThemeToggle';

export function Topbar({ onOpenMenu }: { onOpenMenu: () => void }) {
  const [term, setTerm] = useState('');
  const navigate = useNavigate();

  const submit = (event: FormEvent) => {
    event.preventDefault();
    const q = term.trim();
    navigate(q ? `/customers?q=${encodeURIComponent(q)}` : '/customers');
    setTerm('');
  };

  return (
    <header className="sticky top-0 z-30 flex h-14 items-center gap-2 border-b border-slate-200 bg-surface/85 px-4 backdrop-blur supports-[backdrop-filter]:bg-surface/70 sm:gap-3 sm:px-6 lg:px-8">
      <button
        type="button"
        onClick={onOpenMenu}
        aria-label="Open navigation menu"
        className="-ml-1 grid h-9 w-9 place-items-center rounded-lg text-slate-700 hover:bg-slate-100 lg:hidden"
      >
        <Menu className="h-5 w-5" aria-hidden="true" />
      </button>
      <span className="flex items-center gap-2 lg:hidden">
        <BrandMark className="h-6 w-6" />
        <span className="hidden text-base font-semibold tracking-tight text-slate-900 sm:inline md:hidden">TriChurn</span>
      </span>
      <div className="hidden min-w-0 flex-1 md:block">
        <Breadcrumbs />
      </div>
      <form onSubmit={submit} role="search" className="ml-auto flex w-full max-w-xs items-center md:ml-0">
        <label htmlFor="global-search" className="sr-only">
          Search customers by ID
        </label>
        <div className="relative w-full">
          <Search className="pointer-events-none absolute left-3 top-2.5 h-4 w-4 text-slate-400" aria-hidden="true" />
          <input
            id="global-search"
            type="search"
            value={term}
            onChange={(e) => setTerm(e.target.value)}
            placeholder="Search customer ID…"
            className="w-full rounded-lg border border-slate-200 bg-sunken py-1.5 pl-9 pr-3 text-sm"
          />
        </div>
      </form>
      <ThemeToggle />
      <div className="flex items-center gap-2 rounded-full border border-slate-200 py-0.5 pl-0.5 text-sm text-slate-700 lg:pr-3">
        <span className="grid h-7 w-7 place-items-center rounded-full bg-brand-100 text-brand-700" aria-hidden="true">
          <User className="h-4 w-4" />
        </span>
        <span className="hidden lg:inline">Retention Analyst</span>
      </div>
    </header>
  );
}
