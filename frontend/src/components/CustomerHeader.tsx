import { ArrowLeft } from 'lucide-react';
import { Link } from 'react-router-dom';
import type { IntelligenceResult } from '../types';
import { DecisionBadge } from './DecisionBadge';
import { RiskBadge } from './RiskBadge';
import { SegmentBadge } from './SegmentBadge';

export function CustomerHeader({ result }: { result: IntelligenceResult }) {
  return (
    <div className="mb-6">
      <Link to="/customers" className="inline-flex items-center gap-1 text-sm font-medium text-brand-700 hover:underline">
        <ArrowLeft className="h-4 w-4" aria-hidden="true" /> All customers
      </Link>
      <div className="mt-3 flex flex-wrap items-center gap-3">
        <h1 className="text-[26px] font-semibold tracking-tight text-slate-900">{result.prediction.customerId}</h1>
        <RiskBadge band={result.prediction.riskBand} />
        <SegmentBadge segmentId={result.segment.segmentId} label={result.segment.label} />
        <DecisionBadge decision={result.business.decision} />
      </div>
      <p className="mt-1 text-sm text-slate-600">
        Model {result.prediction.modelVersion} · Scored {result.prediction.scoredAt}
      </p>
    </div>
  );
}
