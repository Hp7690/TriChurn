import { Activity, Calculator, ChevronRight, GitBranch, Search, ShieldCheck } from 'lucide-react';
import { Fragment } from 'react';

const STEPS = [
  { label: 'Predict', icon: Activity },
  { label: 'Explain', icon: Search },
  { label: 'Quantify', icon: Calculator },
  { label: 'Decide', icon: GitBranch },
  { label: 'Retain', icon: ShieldCheck },
];

export function PipelineStrip() {
  return (
    <ol aria-label="TriChurn pipeline" className="mb-6 flex flex-wrap items-center gap-1.5 text-sm">
      {STEPS.map(({ label, icon: Icon }, index) => (
        <Fragment key={label}>
          <li className="inline-flex items-center gap-1.5 rounded-full border border-slate-200 bg-surface px-3 py-1 text-xs font-medium text-slate-700 shadow-sm">
            <Icon className="h-3.5 w-3.5 text-brand-600" aria-hidden="true" />
            {label}
          </li>
          {index < STEPS.length - 1 && <ChevronRight className="h-3.5 w-3.5 text-slate-400" aria-hidden="true" />}
        </Fragment>
      ))}
    </ol>
  );
}
