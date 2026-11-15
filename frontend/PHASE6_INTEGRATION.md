# Connecting Phase 6 (FastAPI) later

Today:   `React UI → IntelligenceService → MockDataProvider`
Future:  `React UI → IntelligenceService → FastAPIDataProvider → Phase 6 API → Phase 1–5`

No page or component changes. Only these files are touched.

## 1. Know the contract
`src/services/api/contract.ts` lists the expected endpoints:

```
GET  /api/v1/health        GET  /api/v1/readiness
POST /api/v1/prediction    POST /api/v1/explainability
POST /api/v1/business      POST /api/v1/segmentation
POST /api/v1/intelligence
```

## 2. Finish `src/services/adapters/FastAPIDataProvider.ts`
It already implements `DataProvider` and `getHealth()`. Every other method currently rejects with `ProviderNotReadyError`. For each method:

| `DataProvider` method | Suggested mapping |
|---|---|
| `getCustomer(id)` | `POST /api/v1/intelligence` → map response to `IntelligenceResult`. Map HTTP 404 → `NotFoundError`. |
| `listCustomers(query)` | Needs a customer source (Phase 6 does not list customers yet). Either add a list endpoint in Phase 6, or call `intelligence` per customer and use `queryCustomers` from `services/aggregations.ts`. |
| `getDashboard()`, `getSegments()`, `getInsights()` | Build from the same per-customer results with `buildDashboard`, `buildSegmentOverview`, `buildInsights` (pure, provider-agnostic) — or call dedicated endpoints if Phase 6 adds them. |
| `getActions()`, `runWhatIf()` | Map to the Phase 4 `business` endpoint (action catalogue and ENB calculation must come from Phase 4, not the UI). |
| `getModelInfo()` | Map from Phase 6 metadata / `readiness`. |

Write one mapper function per response (API DTO → types in `src/types`). Convert axios errors to `ApiError`.

## 3. Flip the switch
In `frontend/.env`:

```
VITE_DATA_PROVIDER=fastapi
VITE_API_BASE_URL=http://localhost:8000
```

`src/services/index.ts` (`createDataProvider`) is the only place that picks the provider. CORS must be enabled on the Phase 6 API for the dev origin.

## 4. Verify
- Add adapter tests with mocked axios, asserting each mapper yields valid `src/types` objects.
- Run `npm run build && npm run test && npm run lint`.
- The `DEMO DATA` banner disappears automatically because `mode` becomes `live`.

## Do not
Recompute business values or SHAP in the UI, or import mock data from pages/components.
