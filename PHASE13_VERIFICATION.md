# Phase 13 verification report

All results below were produced by commands actually run. Anything not run is listed under "Not verified".

## Method
The uploaded `TriChurn_Phase9_Handoff.zip` (which contains **Phases 1-7 only**, not Phase 9) was extracted to a scratch
folder. The existing test suites were run on it **before** adding Phase 13 (baseline). The overlay was then applied with
`scripts/integrate_phase13.py --apply` and the same suites were run again. Nothing was run against your current local
Phase 9 project.

Environment: Python 3.12.3, fastapi 0.162.4, starlette 1.10.0, pydantic 2.14.3, PyYAML 6.0.3, httpx 0.28.1,
pytest 9.2.0, ruff 0.17.4, pandas 3.0.6, numpy 2.5.4, scikit-learn 1.9.1, xgboost 3.4.1, shap 0.54.1; Node 22.23.4,
Vite 5.4.21, Vitest 2.1.9. Frontend dependencies were installed with `npm ci` from the project's own lockfile (no changes).

## Locked artifact hashes (SHA-256)
| Artifact | Expected | Result |
|---|---|---|
| `models/trichurn_churn_model_v2.0.0.joblib` (Phase 2) | `db399a55f650c6681e1caaf52257f909777e2c5fada3af5911370ddf5b8ff1ad` | **OK before and after integration** |
| `models/trichurn_segmentation_v5.0.0.joblib` (Phase 5) | `38423c9cf19b05aa35b72acd44ea3a8af4c3775a1e6cf2bb739ee1972dc05927` | **OK before and after integration** |

Checked by `scripts/verify_phase13_locked_artifacts.py` (exit 0) and by the integration script. This covers the snapshot
copy only; run the script on your own project.

## New tests
| Suite | Result |
|---|---|
| `tests/unit/test_experience_config.py` | 27 passed |
| `tests/unit/test_experience_validation.py` | 57 passed |
| `tests/unit/test_experience_lifecycle.py` | 33 passed (includes a recount against the real Telco CSV) |
| `tests/unit/test_experience_surveys.py` | 17 passed |
| `tests/unit/test_experience_foundations.py` | 27 passed |
| `tests/unit/test_phase13_locked_artifacts.py` | 3 passed (includes the real hashes) |
| `tests/experience_api/test_experience_api.py` | 55 passed |
| `tests/experience_api/test_experience_integration.py` | 4 passed (runs against the patched `app/main.py`) |
| `frontend/src/__tests__/experience.test.tsx` | 31 passed |
| **Total new** | **254 passed, 0 failed, 0 skipped** |

## Regression: existing suites, before vs after
| Suite | Baseline (snapshot) | After Phase 13 | Verdict |
|---|---|---|---|
| Backend `tests/unit` (excl. slow files) | 605 passed, 1 failed | 769 passed, 1 failed | +164 = new unit tests; **same single failure** |
| Backend shap / training / tuning | 69 passed | 69 passed | identical |
| Backend `tests/integration` | 28 passed | 28 passed | identical |
| Backend `tests/api` | **cannot be collected** (`ModuleNotFoundError: tests.support`) | same | **never run**; the snapshot lacks `tests/support/` |
| Frontend Vitest | 39 passed, 2 failed | 70 passed, 2 failed | +31 = new tests; **same 2 failures** |
| ESLint | 1 error | 1 error | identical; none in Phase 13 files |
| `tsc --noEmit` | pass | pass | |
| `npm run build` | pass | pass | |

**Pre-existing failures (present before Phase 13, not caused or hidden by it, not modified):**
* `tests/unit/test_phase6_architecture.py::test_the_real_adapter_is_not_a_test_double_and_the_fake_lives_in_tests_only`: needs the missing `tests/support/fake_adapter.py`.
* `src/__tests__/pages.test.tsx` "what-if page loads, labels itself as a scenario and runs a scenario".
* `src/__tests__/provider.test.ts` "FastAPIDataProvider is an unconnected skeleton and does not touch the network for data methods".
* ESLint `no-extra-boolean-cast` at `src/services/adapters/FastAPIDataProvider.ts:148`.

## Static checks
`ruff check` on `app/`, `trichurn_experience/`, `scripts/`, `tests/experience_api/` and the new unit tests: all checks passed (the project's ruff configuration, unchanged). `python -m compileall` on the new packages: ok.

## Live end-to-end check
The integrated app was started with `uvicorn app.main:app` and called over HTTP on the real Telco CSV:
`/api/v1/liveness` 200 and `/api/v1/readiness` 200; `/experience/availability`: lifecycle AVAILABLE, six other modules
BLOCKED_BY_MISSING_DATA; `/experience/lifecycle`: 7,043 customers, 1,869 churned (26.54%), groups 1,371 / 698 / 1,047 /
1,624 / 2,303; a survey upload with an out-of-scale score and a duplicate id was reported invalid with `persisted: false`;
`/experience/nps/status` returned status BLOCKED with `metrics: null`.

## Issues found during verification
The first integration **failed two existing architecture tests** (`app/` may not import `ml`, and may not compute
business-style metrics). The domain package was therefore moved from `ml/experience/` to the top-level
`trichurn_experience/`; no existing test was changed. All figures above are from the corrected layout.

## Not verified
* Your current Phase 9 project: whether the four patches apply, and whether Phase 9 routes/nav collide. Run the dry run.
* The existing `tests/api` suite (needs `tests/support/`, absent here).
* Windows, Python 3.11, and the lower dependency bounds in `requirements-phase13.txt` (tested on Linux, Python 3.12, newer versions).
* Sentiment, complaint, NPS, CSAT and journey analytics on **real** data (none exists); they were tested with synthetic fixtures.
* Visual design, responsiveness and accessibility by human review or a screen reader; only automated tests and a build were run.
* Load, concurrency and a full penetration test. Not production-ready claim is made.

The package manifest (`PHASE13_MANIFEST_SHA256.txt`) and ZIP integrity check are reported in the delivery message; a file cannot contain the checksum of the archive that contains it.
