# Phase 9 changelog

## Added
* `retention/` (12 modules): config, errors, models, scoring (batch, read-only), prioritization, recommendation, simulator, campaign_store, analytics, summary, uplift_readiness, facade.
* `configs/retention.yaml` (ranking weights, tier cut-offs, limits, uplift-readiness thresholds; no action costs or success rates).
* API: `app/api/routes/retention.py`, `app/api/retention_dependencies.py`, `app/schemas/retention.py`, `app/services/retention_service.py`, `app/core/retention_settings.py` (12 endpoints under `/api/v1/retention`).
* Frontend: `types/retention.ts`, `services/retention/*`, `pages/retention/*` (5 views), `components/retention/badges.tsx`, `charts/RetentionCharts.tsx`, `utils/money.ts`.
* Tests: `tests/retention/*`, `tests/api/test_retention_api.py`, `tests/unit/test_phase9_architecture.py`, `frontend/src/__tests__/retention.test.tsx`, `httpRetentionProvider.test.ts`, test doubles in `frontend/src/test/`.
* `scripts/verify_phase9_integrity.py`, `requirements-api.txt`, reconstructed `docs/phase6.md`, `PHASE9_*.md`, `PHASE9_MANIFEST.txt`, `PHASE9_BASELINE_DIFF.txt`.

## Modified (additive wiring only; before/after hashes in `PHASE9_BASELINE_DIFF.txt`)
* `app/main.py`: import + register the retention router; create the lazy retention service (+4 lines; CRLF line endings preserved).
* `frontend/src/App.tsx`: `/retention/*` routes. `frontend/src/main.tsx`: `RetentionServiceProvider`. `frontend/src/components/Sidebar.tsx`: "Retention" nav item.

## Unchanged
Both model artifacts and sidecars, every Phase 1-5 file, `configs/business.yaml`, `app/core/config.py`, `app/core/errors.py`, all existing tests, `frontend/package.json` and its lockfile.

## Not done / deferred
Uplift modelling (no data), Phase 8, authentication, retraining, Vite/Vitest dependency change (needs npm), restoration of `tests/support/fake_adapter.py`.
