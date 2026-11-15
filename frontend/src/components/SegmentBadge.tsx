import type { SegmentId } from '../types';
import { cn } from '../utils/cn';
import { SEGMENT_BADGE_CLASSES } from '../utils/theme';

export function SegmentBadge({ segmentId, label }: { segmentId: SegmentId; label: string }) {
  return (
    <span
      className={cn(
        'inline-flex items-center whitespace-nowrap rounded-md px-2 py-0.5 text-xs font-medium ring-1 ring-inset',
        SEGMENT_BADGE_CLASSES[segmentId],
      )}
    >
      {label}
    </span>
  );
}
