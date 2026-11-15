# Phase 9 architecture

```
React /retention  ->  HttpRetentionProvider (axios)  ->  /api/v1/retention/*   (app/api/routes/retention.py)
                                                          |
                                         app/services/retention_service.py   (schema mapping, error translation, SHAP via existing adapter)
                                                          |
                                         retention/facade.py                  (framework-free orchestration)
        +-----------------+-----------------+-------------------+----------------+
   scoring.py       prioritization.py   simulator.py     campaign_store.py   uplift_readiness.py
 (locked Phase 2/4/5,   (heuristic rank)   (estimates)       (SQLite)        analytics.py / summary.py
  batch, read-only)
```

Design rules (enforced by `tests/unit/test_phase6_architecture.py` and `tests/unit/test_phase9_architecture.py`):
* `app/` stays thin: no `ml`, pandas, numpy or business arithmetic. All arithmetic lives in `retention/`.
* `retention/` never imports `app`, FastAPI or pydantic; `ml` is imported only inside `ArtifactPortfolioProvider._build`.
* Nothing refits, dumps or deletes files; no mlflow/dvc/airflow; no uplift libraries; no random data generators.
* The Phase 6 `Settings`, `ErrorCode` and adapter port are untouched. Phase 9 settings are in `app/core/retention_settings.py`.
* The retention service is built lazily: a missing artifact or bad config returns `503 CAPABILITY_UNAVAILABLE` for retention
  portfolio routes and never affects the Phase 6 endpoints. Campaign routes keep working without the portfolio.

## Scoring (batch, whole dataset)
`ArtifactPortfolioProvider` (once, thread-safe, cached): verifies the Phase 2 SHA-256 pin **before** loading (fail closed),
loads the Phase 2 artifact and the verified Phase 5 artifact, then on the whole frame: `predict_proba` (vectorised),
`BusinessEngine.profile_frame` (Phase 4), `assign_customers` (Phase 5, nearest centroid). No SHAP for the batch.
The 7,043 customers are served from memory with pagination (page_size <= 200); the UI never makes per-customer calls for lists.
Failures raise `PortfolioUnavailableError(reason_code)`; reason codes never contain paths.

## Formulas
Per customer (all from Phase 4 / `ml.business`): `VaR = CLV x p`; `expected_benefit = CLV x p x success_rate`;
`ENB = expected_benefit - action_cost`; decision INTERVENE when the best eligible action has `ENB > 0`
(and Phase 4 policy thresholds are met). Currency: INR as configured in `configs/business.yaml`.

**Priority score (heuristic, 0-100):**
`score = 100 x (w_var x pct(VaR) + w_p x pct(p) + w_enb x pct(max(ENB,0)))`, with `pct` = average-rank percentile over the portfolio,
weights 0.40 / 0.30 / 0.30 (`configs/retention.yaml`). Tiers (INTERVENE customers only): P1 >= 95, P2 >= 90, P3 >= 80, else P4;
DO_NOT_INTERVENE customers are `MONITOR`. Ordering: candidates first, then score descending, ties by customer id.
It is a ranking aid, not a probability, and is not validated against outcomes (stated in every response).

**Recommendation:** the Phase 4 recommended action; alternatives = other eligible actions with their ENB; reasons = Phase 4
decision messages, ineligibility reasons, segment peer note ("n of m candidates in this segment receive X") and, when the existing
`/explain` adapter is available, the top SHAP features that increase churn (with the caveat that SHAP explains the model, not causes).
Responses carry `basis`, `causal_claim=false`, `uplift_available=false`.

**Simulator (per scenario):** over targeted, Phase 4-eligible customers:
`retained_revenue = sum(VaR_i) x success_rate`; `total_cost = cost x n_eligible`; `net = retained_revenue - total_cost`;
`ROI = net / total_cost` (null if cost is 0); `expected_retained_customers = sum(p_i) x success_rate`. Cost and success rate default to
Phase 4 values and may be overridden to explore assumptions (labelled `scenario_override`). Targeting: Phase 4 candidates or any customer,
risk bands, segments, minimum probability, top-N by priority, explicit ids. Results are always `label: ESTIMATE`.
A unit test cross-checks totals against `ml.business.enb.compute_enb`.

## Campaign tracking (SQLite, empty at start)
Tables `campaigns`, `assignments` (customer, group `treatment|control|unspecified`, **estimated** cost/benefit snapshotted from Phase 4 at
assignment time, zero for controls) and `outcomes` (**actual**: outcome `retained|churned|no_response`, optional actual cost and retained
revenue). Estimated and actual live in separate columns and are never mixed or back-filled. Parameterised SQL only; CHECK constraints
enforce enums; one outcome per assignment (history is not rewritten); duplicates and unknown customers are reported, not hidden.
Analytics (`observed_retention_rate`, actual cost/revenue/net/ROI) are `null` until real data exists, and carry the "no uplift is claimed" note.

## Uplift
Audit result: the Telco dataset has 21 standard columns and no treatment/campaign/outcome fields; Phase 4 success rates are assumptions;
the campaign store starts empty. Therefore **no uplift model exists**. `uplift_readiness` reports pass/fail checks (treatment-like columns in
the dataset, >= N treatment and N control assignments, outcome coverage, randomised assignment) and the requirements for future uplift
modelling: a randomised treatment/control design, outcomes for both arms over one window, enough volume, and pre-treatment features.
Even when "ready", the status is `READY_FOR_FEASIBILITY_REVIEW`, not a model.

## Frontend
New: `src/types/retention.ts`, `src/services/retention/*` (provider interface, HTTP provider, context), `src/pages/retention/*`
(Overview, Priorities, Recommendations, Simulator, Campaigns), `src/charts/RetentionCharts.tsx`, `src/utils/money.ts` (INR-aware).
Loading, empty, error (with Retry) and success states use the existing `AsyncBoundary`. There is deliberately no mock provider in application code.
