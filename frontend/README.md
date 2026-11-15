# TriChurn Frontend — Customer Churn Prediction & Intelligence Platform

React + TypeScript + Vite + Tailwind CSS + Recharts + Lucide. Visualises **Predict → Explain → Quantify → Decide → Retain**.

The core intelligence pages (dashboard, customers, segments, insights, what-if, model) read from `IntelligenceService`, which uses `MockDataProvider` (deterministic DEMO data) by default and can be pointed at the FastAPI adapter. Retention, Autonomous, Revenue, Experience and Lifecycle call their own HTTP providers and never substitute demo data; when the API cannot supply something, the page shows the real unavailable, blocked or error state.

Light, dark and system themes are supported (top bar or Settings). See [DESIGN_SYSTEM.md](DESIGN_SYSTEM.md).

## Run

```bash
cd frontend
npm install
npm run dev        # http://localhost:5173
```

## Build, test, lint

```bash
npm run build      # tsc --noEmit && vite build
npm run test       # vitest run
npm run lint       # eslint .
```

## Pages

| Route | Page |
|---|---|
| `/dashboard` | Executive dashboard (6 KPIs, risk / segment / VaR / opportunity charts, recent high-risk table) |
| `/customers` | Customer intelligence: search, risk / segment / probability filters, sorting, pagination |
| `/customers/:customerId` | Overview, business value, SHAP-style explanation, profile |
| `/segments` | The three locked Phase 5 segments, charts, comparison table, segment customers |
| `/insights` | Highest-value-at-risk, highest-VaR, highest-ENB, action summary |
| `/what-if` | Scenario / What-if analysis (Current → Scenario → New ENB → Decision) |
| `/model` | Locked Phase 2 metrics and Phase 5 configuration (read-only) |
| `/retention/*` | Retention overview, priorities, recommendations, simulator, campaigns |
| `/autonomous/*` | Command center, risk monitor, recommendations, approvals, learning, audit |
| `/revenue/*` | Executive, CLV, revenue at risk, upsell & cross-sell, cohorts, forecasting |
| `/experience` | Customer experience data availability (shows blocked / unavailable states as reported) |
| `/experience-lifecycle` | Tenure-based lifecycle analysis (a tenure proxy, not an event-based journey) |
| `/settings` | Appearance (theme), data-source info; developer toggle to simulate API failure |

## Design system

See [DESIGN_SYSTEM.md](DESIGN_SYSTEM.md). Light, dark and system themes; switch in the top bar or under Settings.

## Structure

```
src/
  components/   reusable UI (KpiCard, RiskBadge, CustomerTable, Drawer, ErrorState, ...)
  charts/       Recharts wrappers (ShapChart, SegmentChart, ValueAtRiskChart, ...)
  layouts/      AppLayout (sidebar + topbar)
  pages/        one file per route
  services/
    api/        DataProvider interface, errors, FastAPI contract
    adapters/   MockDataProvider (default), FastAPIDataProvider
    aggregations.ts  pure roll-ups over per-customer results
    IntelligenceService.ts  the only object the UI talks to
    index.ts    <-- THE DATA-SOURCE SWITCH
  data/         deterministic demo dataset + locked model info
  hooks/ utils/ types/ test/ __tests__/
```

## Data source switch

`src/services/index.ts` reads `VITE_DATA_PROVIDER` (`mock` default, or `fastapi`). Copy `.env.example` to `.env` to change it. See `PHASE6_INTEGRATION.md`.

## Mock data

80 demo customers (`TC-1001`…`TC-1080`) generated from a fixed seed — identical on every load, test run and machine. The app shows a **DEMO DATA · MOCK API** banner. Customer-level values (probabilities, CLV, VaR, ENB, SHAP, actions) are illustrative and are **not** Phase 1–5 outputs; only the Phase 2 metrics and Phase 5 configuration on `/model` are the locked values.

Mock-only environment variables: `VITE_MOCK_LATENCY_MS`, `VITE_MOCK_FAIL=always`, or use the toggle in Settings to exercise error and retry UI.

## Out of scope for the frontend

PostgreSQL, MLflow, DVC, Airflow, authentication/JWT, retraining, deployment/CI-CD, new ML models, new segmentation. The frontend never calculates SHAP, trains, or clusters.
