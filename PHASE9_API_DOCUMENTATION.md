# Phase 9 API (prefix `/api/v1/retention`)

Errors use the Phase 6 envelope `{"error": {"code", "message", "details"?}}`. Codes used: `INVALID_INPUT` (422), `NOT_FOUND` (404),
`CAPABILITY_UNAVAILABLE` (503, portfolio or configuration unavailable), `INTERNAL_ERROR` (500). Responses never include paths or stack traces.
Interactive docs: `/docs` (OpenAPI is generated from the schemas in `app/schemas/retention.py`).

| Method & path | Purpose | Notes |
|---|---|---|
| `GET /summary` | Executive summary | Revenue at risk, candidates, P1-P2 customers, per-band and per-segment figures, recommended campaigns with ESTIMATED cost / retained revenue / net / ROI, top 10 priorities. `kind: "estimate"`. |
| `GET /priorities` | Ranked list, paginated | Query: `page>=1`, `page_size 1-200 (25)`, `search`, `risk_band`, `segment_id`, `decision`, `tier`, `min_churn_probability 0-1`, `sort_by` (rank, priority_score, churn_probability, value_at_risk, clv, expected_net_benefit), `descending`. Each item has score, tier, percentiles and `reasons`. |
| `GET /actions` | Phase 4 action catalogue | Single source of truth (`configs/business.yaml`); success rates are assumptions. |
| `GET /customers/{customer_id}/recommendation` | Recommendation with reasons | 404 for unknown customer. `drivers` come from the existing explainability adapter and degrade to `explainability_available=false`. |
| `POST /simulate` | Compare 1-10 scenarios | Body `{"scenarios":[{"action_id", "name?", "cost_override?>=0", "success_rate_override? 0-1", "decision_filter": "intervene|any", "risk_bands?", "segment_ids?", "min_churn_probability?", "top_n?", "customer_ids?"}]}`. Unknown fields rejected. `top_n` selects by priority rank from the matching customers, including when `customer_ids` is supplied. Returns per-scenario estimates, assumption sources, `best_by_net_benefit_index`, `best_by_roi_index`. |
| `POST /campaigns` (201) | Create campaign | `{"name","action_id","campaign_date":"YYYY-MM-DD","randomized?","notes?"}`; requires canonical `YYYY-MM-DD` form and an enabled Phase 4 `action_id`. |
| `GET /campaigns` | List campaigns | Empty list on a fresh database. |
| `GET /campaigns/{campaign_id}` | Campaign performance | Estimated and actual figures in separate fields; `null` where nothing was recorded. |
| `POST /campaigns/{campaign_id}/assignments` | Assign customers | `{"customer_ids":[...<=1000 per request], "group?"}`. Response reports `unknown_customer_ids`, `ineligible_customer_ids` (Phase 4 eligibility, e.g. minimum CLV) and `already_assigned_ids`. Controls get zero estimated cost/benefit. |
| `POST /campaigns/{campaign_id}/outcomes` | Record outcomes | `{"outcomes":[{"customer_id","outcome":"retained|churned|no_response","actual_cost?","actual_retained_revenue?"}]}`. One outcome per assignment; repeats and unassigned customers are reported. Revenue only for `retained`. |
| `GET /analytics` | All campaigns | Totals; actual totals are `null` until recorded. |
| `GET /uplift-readiness` | Readiness checks | `status: NOT_READY` until randomised treatment+control data with outcomes exist; no model is built. |

Example:
```bash
curl -s localhost:8000/api/v1/retention/priorities?page_size=5\&tier=P1
curl -s -X POST localhost:8000/api/v1/retention/simulate -H 'Content-Type: application/json' \
  -d '{"scenarios":[{"action_id":"discount_offer"},{"action_id":"loyalty_offer","success_rate_override":0.2,"top_n":200}]}'
```
Existing endpoints are unchanged. (An OpenAPI snapshot of the Phase 6 API is in `frontend/openapi.json`, UTF-16 encoded, version 6.0.0; it predates Phase 9.)
