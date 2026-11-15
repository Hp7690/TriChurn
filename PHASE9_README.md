# TriChurn Phase 9 - Advanced Retention Intelligence

Phase 9 adds a retention **decision-support** layer to the existing TriChurn application while preserving the locked
Phase 1-8 functionality:

| Capability | Where |
|---|---|
| A. Retention prioritisation (heuristic score + reasons) | `retention/prioritization.py`, `GET /api/v1/retention/priorities` |
| B. Campaign recommendation (Phase 4 actions + reasons + optional SHAP drivers) | `retention/recommendation.py`, `GET /retention/customers/{id}/recommendation` |
| C. What-if simulator (cost, retained revenue, net benefit, ROI, multi-scenario) | `retention/simulator.py`, `POST /retention/simulate` |
| D. Campaign tracking (campaigns, assignments, outcomes, analytics) - starts EMPTY | `retention/campaign_store.py`, `retention/analytics.py` |
| E. Executive insights | `retention/summary.py`, `GET /retention/summary` |
| Uplift **readiness** checks only | `retention/uplift_readiness.py`, `GET /retention/uplift-readiness` |
| Frontend: Retention Intelligence (5 views) | `frontend/src/pages/retention/*`, route `/retention` |

## What Phase 9 does NOT do
* It does **not** build, train or claim an uplift/causal model. The dataset has no treatment or outcome columns
  (audited), and the campaign database starts empty. See "Uplift" in `PHASE9_ARCHITECTURE.md`.
* It does **not** retrain, refit, replace or rewrite either locked model, and invents no financial assumptions:
  action costs, success rates and eligibility come only from `configs/business.yaml` (Phase 4).
* It does **not** depend on Phase 8 / MLflow. Existing Phase 8 functionality and the `/api/v1/model/lifecycle` route
  remain registered; the Phase 8 regression suite is included in the validation report.
* No campaign history is fabricated; no mock mode exists for the retention UI.

## Install and run
```bash
pip install -r requirements.txt -r requirements-api.txt
uvicorn app.main:app --reload                                # API on http://localhost:8000 , docs at /docs
cd frontend && npm install && npm run dev                    # UI on http://localhost:5173 -> /retention
```
Optional settings: `TRICHURN_RETENTION_DB` (default `data/campaigns.sqlite3`, created empty on first use; add it to
`.gitignore`), `TRICHURN_RETENTION_CONFIG` (default `configs/retention.yaml`), `VITE_API_BASE_URL` for the frontend.
The first retention request scores all 7,043 customers once in batch (about 3 seconds on the audit machine) and
caches the result; restart the API to rescore.

## Verify
```bash
python -m ruff check app/api/routes/retention.py app/api/retention_dependencies.py app/core/retention_settings.py app/schemas/retention.py app/services/retention_service.py app/main.py retention
python -m pytest -q
cd frontend && npm run typecheck && npm run build && npm test && npm run lint
```
The full Python suite was run on Windows with `PYTHONIOENCODING=utf-8` because the Phase 4 demo prints the INR symbol
and the default cp1252 console cannot encode it. The optional integrity script still expects a missing handoff manifest
and predates the Phase 9 audit changes; artifact hashes are checked by the architecture tests. See
`PHASE9_TEST_REPORT.md` for exact results and remaining issues.

## Locked artifacts (unchanged)
| File | SHA-256 |
|---|---|
| `models/trichurn_churn_model_v2.0.0.joblib` | `db399a55f650c6681e1caaf52257f909777e2c5fada3af5911370ddf5b8ff1ad` |
| `models/trichurn_segmentation_v5.0.0.joblib` | `38423c9cf19b05aa35b72acd44ea3a8af4c3775a1e6cf2bb739ee1972dc05927` |

## Integration and preservation
The API router is registered alongside the existing routes, including `model_lifecycle`; the frontend routes and provider
are additive. Phase 1-8 configurations, APIs, model artifacts and application behavior are preserved. The audit fixes
and test changes are listed in `PHASE9_TEST_REPORT.md`.

## Known issues and limitations
1. The Phase 4 demo script `scripts/run_phase4.py` can raise `UnicodeEncodeError` when run from a default Windows
   cp1252 console because it prints `₹`. The complete test suite passes with `PYTHONIOENCODING=utf-8`; the unrelated
   Phase 4 script was not changed in this Phase 9 audit.
2. Priority tiers and weights are heuristic defaults in `configs/retention.yaml`; they are not statistically validated.
3. Estimates assume Phase 4 success rates, which are assumptions rather than measured effects. No causal uplift model
   exists or is claimed.
4. Campaign persistence uses single-node SQLite, permits one immutable outcome per assignment, and has no authentication.
   Do not expose the API publicly without an independently designed authentication/authorization layer.
5. `npm audit` and `pip-audit` were not run as part of this audit.
