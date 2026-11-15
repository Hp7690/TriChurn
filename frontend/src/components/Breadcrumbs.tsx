import { ChevronRight } from 'lucide-react';
import { Fragment } from 'react';
import { Link, useLocation } from 'react-router-dom';
import { DETAIL_LABELS, groupLabelFor, SEGMENT_LABELS, SUB_SEGMENT_LABELS } from './navConfig';

interface Crumb {
  label: string;
  to?: string;
  /** The navigation group (Analyze, Act, ...). Hidden on narrower screens to give the page trail room. */
  group?: boolean;
}

/** Builds the trail from the static route map only; ids from the URL are never shown. */
export function buildCrumbs(pathname: string): Crumb[] {
  const parts = pathname.split('/').filter(Boolean);
  const root = parts[0];
  if (!root || !(root in SEGMENT_LABELS)) return [];

  const crumbs: Crumb[] = [];
  const group = groupLabelFor(pathname);
  if (group) crumbs.push({ label: group, group: true });

  const second = parts[1];
  const third = parts[2];
  const secondKey = second ? `${root}/${second}` : null;
  const subLabel = secondKey !== null ? SUB_SEGMENT_LABELS[secondKey] : undefined;

  crumbs.push({ label: SEGMENT_LABELS[root], to: second ? `/${root}` : undefined });
  if (secondKey !== null && subLabel !== undefined) {
    // e.g. /retention/recommendations/:customerId
    const detail = third !== undefined ? DETAIL_LABELS[secondKey] : undefined;
    crumbs.push({ label: subLabel, to: detail ? `/${secondKey}` : undefined });
    if (detail) crumbs.push({ label: detail });
  } else if (second !== undefined && DETAIL_LABELS[root] !== undefined) {
    // e.g. /customers/:customerId
    crumbs.push({ label: DETAIL_LABELS[root] });
  }
  return crumbs;
}

export function Breadcrumbs() {
  const { pathname } = useLocation();
  const crumbs = buildCrumbs(pathname);
  if (crumbs.length === 0) return null;
  return (
    <nav aria-label="Breadcrumb" className="min-w-0">
      <ol className="flex min-w-0 items-center gap-1.5 text-sm">
        {crumbs.map((crumb, index) => {
          const last = index === crumbs.length - 1;
          return (
            <Fragment key={`${crumb.label}-${index}`}>
              {index > 0 && (
                <ChevronRight
                  className={`h-3.5 w-3.5 shrink-0 text-slate-400 ${crumbs[index - 1].group ? 'hidden xl:block' : ''}`}
                  aria-hidden="true"
                />
              )}
              <li className={`${last ? 'shrink-0' : 'min-w-0 truncate'} ${crumb.group ? 'hidden xl:block' : ''}`}>
                {crumb.to && !last ? (
                  <Link to={crumb.to} className="rounded text-slate-500 transition-colors hover:text-slate-900">
                    {crumb.label}
                  </Link>
                ) : (
                  <span
                    aria-current={last ? 'page' : undefined}
                    className={last ? 'font-medium text-slate-900' : 'text-slate-500'}
                  >
                    {crumb.label}
                  </span>
                )}
              </li>
            </Fragment>
          );
        })}
      </ol>
    </nav>
  );
}
