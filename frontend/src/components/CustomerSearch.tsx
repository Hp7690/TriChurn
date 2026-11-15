import { Search } from 'lucide-react';

interface CustomerSearchProps {
  value: string;
  onChange: (value: string) => void;
  id?: string;
  label?: string;
  placeholder?: string;
}

export function CustomerSearch({
  value,
  onChange,
  id = 'customer-search',
  label = 'Search customer ID',
  placeholder = 'e.g. TC-1005',
}: CustomerSearchProps) {
  return (
    <div>
      <label htmlFor={id} className="field-label">
        {label}
      </label>
      <div className="relative">
        <Search className="pointer-events-none absolute left-3 top-2.5 h-4 w-4 text-slate-400" aria-hidden="true" />
        <input
          id={id}
          type="search"
          value={value}
          onChange={(event) => onChange(event.target.value)}
          placeholder={placeholder}
          autoComplete="off"
          className="field pl-9"
        />
      </div>
    </div>
  );
}
