import { useState } from 'react';
import { UNAVAILABLE_TEXT } from './format';

export interface BarDatum {
  label: string;
  value: number | null;
  display?: string;
}

/** Horizontal bar chart (SVG, no chart dependency). Hover or focus a bar to see its value; null renders "Unavailable". */
export function BarChart({ data, title, valueLabel, format }: { data: BarDatum[]; title: string; valueLabel: string; format?: (v: number) => string }) {
  const [active, setActive] = useState<string | null>(null);
  const known = data.filter((d) => d.value !== null) as Array<BarDatum & { value: number }>;
  if (known.length === 0) {
    return <p role="note" className="rounded-lg bg-slate-50 px-4 py-6 text-center text-sm text-slate-600">{title}: {UNAVAILABLE_TEXT} (no valid values).</p>;
  }
  const max = Math.max(...known.map((d) => d.value), 0) || 1;
  const fmt = format ?? ((v: number) => v.toLocaleString('en-US', { maximumFractionDigits: 2 }));
  return (
    <figure aria-label={title} data-testid="bar-chart">
      <figcaption className="sr-only">{title} ({valueLabel})</figcaption>
      <ul className="space-y-2">
        {data.map((d) => {
          const pct = d.value === null ? 0 : Math.max((d.value / max) * 100, d.value > 0 ? 1.5 : 0);
          const text = d.value === null ? UNAVAILABLE_TEXT : d.display ?? fmt(d.value);
          return (
            <li key={d.label} className="grid grid-cols-[8rem_1fr_6rem] items-center gap-2 text-xs">
              <span className="truncate text-slate-700" title={d.label}>{d.label}</span>
              <svg role="img" aria-label={`${d.label}: ${text} ${valueLabel}`} viewBox="0 0 100 8" preserveAspectRatio="none" className="h-4 w-full rounded bg-slate-100" tabIndex={0}
                onMouseEnter={() => setActive(d.label)} onMouseLeave={() => setActive(null)} onFocus={() => setActive(d.label)} onBlur={() => setActive(null)}>
                <title>{`${d.label}: ${text}`}</title>
                <rect x="0" y="0" width={pct} height="8" className={active === d.label ? 'fill-indigo-700' : 'fill-indigo-500'} />
              </svg>
              <span className="text-right tabular-nums text-slate-800" data-testid="bar-value">{text}</span>
            </li>
          );
        })}
      </ul>
      <p className="mt-2 min-h-4 text-xs text-slate-500" aria-live="polite">{active ? `${active}: ${text(data, active, fmt)} ${valueLabel}` : `Hover or focus a bar for detail. Values: ${valueLabel}.`}</p>
    </figure>
  );
}

function text(data: BarDatum[], label: string, fmt: (v: number) => string): string {
  const d = data.find((x) => x.label === label);
  return d?.value === null || d === undefined ? UNAVAILABLE_TEXT : d.display ?? fmt(d.value);
}

/** Vertical histogram of equal-width bins. */
export function Histogram({ bins, title, xLabel }: { bins: Array<{ lower: number; upper: number; count: number }>; title: string; xLabel: string }) {
  const [active, setActive] = useState<number | null>(null);
  if (bins.length === 0) return <p role="note" className="rounded-lg bg-slate-50 px-4 py-6 text-center text-sm text-slate-600">{title}: {UNAVAILABLE_TEXT} (no valid values).</p>;
  const max = Math.max(...bins.map((b) => b.count), 1);
  const w = 100 / bins.length;
  return (
    <figure aria-label={title} data-testid="histogram">
      <svg viewBox="0 0 100 40" className="h-40 w-full" role="img" aria-label={`${title}: ${bins.length} bins`}>
        {bins.map((b, i) => {
          const h = (b.count / max) * 36;
          return (
            <rect key={`${b.lower}-${b.upper}`} x={i * w + 0.5} y={38 - h} width={w - 1} height={h} tabIndex={0}
              className={active === i ? 'fill-indigo-700' : 'fill-indigo-500'}
              onMouseEnter={() => setActive(i)} onMouseLeave={() => setActive(null)} onFocus={() => setActive(i)} onBlur={() => setActive(null)}>
              <title>{`${b.lower.toLocaleString('en-US')} – ${b.upper.toLocaleString('en-US')}: ${b.count.toLocaleString('en-US')} customers`}</title>
            </rect>
          );
        })}
        <line x1="0" y1="38" x2="100" y2="38" className="stroke-slate-300" strokeWidth="0.3" />
      </svg>
      <figcaption className="mt-1 text-xs text-slate-600" aria-live="polite">
        {active !== null && bins[active]
          ? `${bins[active].lower.toLocaleString('en-US')} – ${bins[active].upper.toLocaleString('en-US')}: ${bins[active].count.toLocaleString('en-US')} customers`
          : `${xLabel}. Hover or focus a bar for detail.`}
      </figcaption>
    </figure>
  );
}
