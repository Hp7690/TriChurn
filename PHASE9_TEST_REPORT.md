# Phase 9 integration audit and test report

**Status: Phase 9 integration validated.** The audit preserved the Phase 1-8 routes, settings, model artifacts and frontend
providers. The complete Python suite and frontend checks were executed; commands and environment are recorded below.

## Findings and fixes
| Area | Finding | Resolution |
|---|---|---|
| Priorities UI | A description-only `Card` did not render its description, hiding the heuristic-score disclaimer. | Render the card header when a description is provided; retention page test now passes. |
| Retention HTTP provider | Whitespace-only search values were sent as literal filters when called directly. | Trim and omit empty search values. |
| Simulator | `top_n` was documented as priority-ranked, but explicit `customer_ids` preserved caller order. | Apply `top_n` in priority-index order and add regression coverage. |
| Campaign persistence | Store accepted negative/non-finite estimated benefits and invalid churn probabilities; non-canonical ISO week dates could pass as campaign dates. | Validate finite non-negative estimates, probability range, and canonical `YYYY-MM-DD` format before insertion. |
| Phase 8 lifecycle test | Its route-set assertion allowed only the model-lifecycle endpoint, so it rejected the intentional Phase 9 routes. | Keep the Phase 1-6 and model-lifecycle checks, and assert the exact additive Phase 9 route set. |

## Executed checks
| Check | Result |
|---|---|
| Full Python test suite | **1,063 collected; completed successfully** with `PYTHONIOENCODING=utf-8`. This includes Phase 8 lifecycle, integrity, model-loading, registry and architecture tests. |
| Phase 9 focused tests | **144 tests completed successfully** across `tests/retention`, `tests/api/test_retention_api.py`, and `tests/unit/test_phase9_architecture.py`. |
| Additive route-preservation regression | **1 test passed** in `tests/phase8/test_api_lifecycle.py`, asserting the original API, model-lifecycle route, and exact Phase 9 route set. |
| Python syntax | `python -m compileall -q app retention` passed. |
| Ruff | Focused Phase 9 backend files and `retention/` passed `python -m ruff check`. |
| Frontend unit tests | **67 tests passed** across 5 files, including all 20 retention UI tests and 5 HTTP provider tests. |
| Frontend TypeScript and production build | `npm run build` passed (`tsc --noEmit` and Vite production build). |
| Frontend lint | `npm run lint` passed. |
| Phase 2 model SHA-256 | `db399a55f650c6681e1caaf52257f909777e2c5fada3af5911370ddf5b8ff1ad` verified unchanged. |
| Phase 5 segmentation SHA-256 | `38423c9cf19b05aa35b72acd44ea3a8af4c3775a1e6cf2bb739ee1972dc05927` verified unchanged. |
| Optional Phase 9 integrity script | Not run: its default `HANDOFF_SHA256.txt` manifest is absent, and its allow-list predates the requested audit fixes. Artifact hashes were independently checked and are enforced in the passing Phase 9 architecture tests. |

## Environment note and remaining concerns
* Running the full suite with the default Windows cp1252 console produced a pre-existing `UnicodeEncodeError` in
  `scripts/run_phase4.py` when it prints `₹`. The complete suite passed with `PYTHONIOENCODING=utf-8`; the unrelated Phase 4
  script was not changed as part of this audit.
* The expected Phase 8 test for a single model-lifecycle addition was updated to account for the explicitly registered Phase 9
  endpoints. Existing Phase 1-8 endpoint and lifecycle behavior remains covered and passed.
* Priority scores are heuristic rankings, churn probabilities come from the locked Phase 2 model, and financial impact remains
  an estimate under Phase 4 assumptions. No trained uplift model is implemented or claimed.
* Campaign data is stored in single-node SQLite; outcomes are append-only and limited to one outcome per assignment. There is
  no authentication/authorization layer, so do not expose these endpoints publicly without adding one.
* `npm audit` and `pip-audit` were not run. Test output included upstream Starlette/httpx and MLflow/SQLAlchemy deprecation
  warnings; no test failed because of these warnings.
