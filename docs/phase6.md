# Phase 6 - API layer (reconstructed reference)

> `docs/phase6.md` is referenced by `app/core/config.py` but was **missing from the Phase 9 handoff archive**.
> This file was reconstructed during the Phase 9 audit from the code in `app/` and `phase6/`; it is a summary, not the
> original document. If you have the original, keep it and delete this file.

* Entry point: `app.main:create_app` (module-level `app = create_app()`), run with `uvicorn app.main:app`.
* All routes are under `/api/v1`: `GET /health`, `GET /liveness`, `GET /readiness`, `POST /predict`,
  `POST /explain`, `POST /business`, `POST /segment`, `POST /customer-intelligence`.
* Layers: `app/api` (routes) -> `app/services` -> `app/services/adapters` (the ONLY place that imports `ml`).
  Architecture rules are enforced by `tests/unit/test_phase6_architecture.py`.
* Errors use one envelope: `{"error": {"code", "message", "details"?, "error_id"?}}` with codes `INVALID_INPUT`,
  `NOT_FOUND`, `METHOD_NOT_ALLOWED`, `INTEGRATION_NOT_CONFIGURED`, `ARTIFACT_UNAVAILABLE`, `CAPABILITY_UNAVAILABLE`,
  `INCONSISTENT_RESULTS`, `INTERNAL_ERROR`.
* Settings come from `TRICHURN_*` environment variables (`ENVIRONMENT`, `PROJECT_ROOT`, `PHASE2_MODEL`,
  `PHASE2_SHA256`, `PHASE5_MODEL`, `PHASE5_SHA256`, `DATASET_CSV`, `DATASET_SPEC`, `ADAPTER_FACTORY`, `ENABLE_DOCS`).
  The Phase 2 artifact digest is pinned to `db399a55...8ff1ad`.
* Dependencies were not declared in `requirements.txt`; see `requirements-api.txt` (added in Phase 9).
* `tests/api/*` import `tests/support/fake_adapter.py`, which is **also missing from the handoff**, so those tests
  cannot run until it is restored.
