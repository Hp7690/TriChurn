# TriChurn design system

## How theming works
- All colours are CSS variables in `src/index.css` (RGB channels, so opacity modifiers work). `:root` is light, `:root.dark` is dark.
- `tailwind.config.js` points the existing `slate`, `brand`, `rose`, `amber`, `emerald`, `indigo`, `teal`, `orange` and `fuchsia` scales at those variables, so every existing class (`text-slate-600`, `bg-rose-50`) follows the theme. New semantic colours: `canvas`, `surface`, `sunken`, `overlay`.
- Scale roles: 50-200 surfaces, 300 borders, 400-500 muted text, 600-900 text. Dark mode swaps those roles; it is not a mechanical inversion.
- Do not use `hover:bg-brand-700` / `hover:bg-rose-700` for buttons (those shades are text colours in dark mode). Use `.btn-primary` / `.btn-danger`.
- Theme state: `src/theme/themeStore.ts` (`useTheme()`), persisted under `trichurn-theme`; `index.html` applies it before first paint.

## Tokens
| Token | Where |
|---|---|
| Colour, shadow (`shadow-sm..xl`), chart colours | `src/index.css` variables |
| Radius | `rounded-lg` 8px controls, `rounded-xl` 14px cards, `rounded-2xl` modals |
| Type | IBM Plex Sans / Mono (Google Fonts link in `index.html`; falls back to system fonts) |
| Motion | `animate-slide-in`, `slide-in-right`, `pop-in`; all disabled under `prefers-reduced-motion` |

## Components
| Need | Use |
|---|---|
| Buttons | `<Button variant size>` or classes `btn btn-primary|secondary|danger|ghost [btn-sm]` |
| Inputs, selects, textareas | class `field` + `field-label` (native controls are also themed globally) |
| Cards, KPIs | `Card`, `KpiCard`, `MetricCard`, `RetentionActionCard` |
| Tables | `CustomerTable` pattern: `rounded-xl border`, `bg-sunken` header, `divide-slate-100` rows |
| Badges | `RiskBadge`, `SegmentBadge`, `DecisionBadge`, `ExperienceStatusBadge` |
| Tabs | `SectionTabs` (route-backed) |
| Overlays | `Modal` (short tasks), `Drawer` (forms, navigation); both trap focus, lock scroll, close on Esc |
| States | `LoadingSkeleton`, `EmptyState`, `ErrorState`, `AsyncBoundary`, `ChartFrame` |
| Shell | `AppLayout`, `Sidebar` (groups in `navConfig.ts`), `Topbar`, `Breadcrumbs` |

## Notes
- A base rule gives every `.grid` a single `minmax(0, 1fr)` column; breakpoint classes such as `lg:grid-cols-2` still override it. This stops wide tables from forcing horizontal page scroll on phones.
- Autonomy priorities (high / medium / low) use `PriorityBadge`; the retention `TierBadge` is only for P1 / P2 / Monitor.
- The top bar yields space responsively: the wordmark shows only between 640px and 767px, the group crumb appears from `xl`, and the analyst label from `lg`.
