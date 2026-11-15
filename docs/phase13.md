# Phase 13 - Customer Experience & Sentiment Intelligence

Phase 13 is an **additive overlay**. It adds a foundation for feedback, sentiment, complaint, NPS, CSAT and journey
analytics, plus a **tenure-based lifecycle proxy** that works on the existing Telco dataset. It changes no model, no
existing endpoint, no existing route and no dependency.

## 1. The one rule that shapes everything

The IBM Telco dataset (7,043 customers, 21 columns) has **no feedback text, no tickets, no survey scores and no event
timestamps**. Therefore:

| Module | Telco data alone | With real data configured |
|---|---|---|
| Lifecycle (tenure proxy) | **AVAILABLE** | n/a |
| Feedback data | BLOCKED_BY_MISSING_DATA | AVAILABLE (validated, record and label counts) |
| Sentiment | BLOCKED_BY_MISSING_DATA | PARTIALLY_AVAILABLE; AVAILABLE only if a model is also registered **in code** |
| Complaints | BLOCKED_BY_MISSING_DATA | AVAILABLE (counts, resolution time, SLA) |
| NPS / CSAT | BLOCKED_BY_MISSING_DATA | AVAILABLE (formula over valid responses) |
| Journey | BLOCKED_BY_MISSING_DATA | AVAILABLE (ordered sequences, aggregation) |

Blocked modules return **no metrics at all** (`metrics: null`), never zeros and never sample values. Nothing is inferred
from churn labels, churn probability, `TechSupport` or any other Telco column. No sentiment model is trained or shipped.

Statuses: `AVAILABLE`, `PARTIALLY_AVAILABLE`, `BLOCKED_BY_MISSING_DATA`, `DISABLED`, `VALIDATION_FAILED`.
A configured dataset that fails validation is `VALIDATION_FAILED` and **no analytics are computed from it**.

## 2. Architecture

```
frontend (React)  ->  /api/v1/experience/*  ->  app/api/routes/experience.py
                                                  -> app/services/experience_service.py
                                                       -> trichurn_experience/   (pure Python + PyYAML)
```

| Path | Role |
|---|---|
| `trichurn_experience/` | Domain logic: `config`, `schemas`, `validation`, `lifecycle`, `surveys`, `complaints`, `journey`, `sentiment`, `requirements`. Standard library + PyYAML only. |
| `app/services/experience_service.py` | Availability, lifecycle, upload validation, per-module status, caching by file mtime/size. No persistence. |
| `app/api/routes/experience.py` | Router, request-size guard, `register_experience(app, settings)`. |
| `app/schemas/experience.py` | Pydantic request/response models. |
| `configs/experience.yaml` | Policy only: limits, thresholds, scales. Every dataset is `null` by default. |
| `frontend/src/pages/ExperiencePage.tsx`, `LifecyclePage.tsx` | Experience Command Center and lifecycle analysis. |

### Why `trichurn_experience/` and not `ml/experience/`
The first design used `ml/experience/`. The project's own architecture test (`tests/unit/test_phase6_architecture.py`)
rejects it: only the Phase 15 adapter may import `ml`, and nothing under `app/` may compute business-style metrics.
Rather than weaken that test or rename variables to dodge it, the domain logic lives in its own top-level package, which
keeps the API layer thin and leaves `ml/` completely untouched. If you prefer another location, move the package and
update the imports; the architecture test will tell you if the move is compatible.

### Failure isolation
`register_experience()` never raises for a bad experience configuration. The existing API keeps starting and the
experience endpoints report `VALIDATION_FAILED` with the reason.

## 3. API (`/api/v1/experience`)

All errors use the project envelope `{"error": {"code", "message"}}`. Uploads are sent as JSON text and **never stored**.

| Method and path | Purpose |
|---|---|
| `GET /availability` | Status of all seven modules, lifecycle summary, data-quality block, notices. |
| `GET /lifecycle` | Tenure lifecycle proxy (see section 4). |
| `POST /validate-feedback` `/validate-tickets` `/validate-events` | Body `{"format": "csv"\|"json", "content": "<text>"}`. Returns a validation report. |
| `POST /validate-survey` | Same body plus `"survey_type": "nps"\|"csat"`. |
| `POST /data-quality` | Same body plus `"dataset": "feedback"\|"tickets"\|"nps"\|"csat"\|"events"`. Report plus completeness, valid-row and duplicate rates. |
| `GET /sentiment/status` `/complaints/status` `/journey/status` | Module status, requirements, validation summary, metrics when AVAILABLE. |
| `GET /nps/status` `/csat/status` | Same, with optional `period_start` and `period_end` (ISO 8601). |

Status codes: `200` success (including blocked modules); `413` content over the size, row or column limit; `422` invalid
body, unparseable content, bad period or unknown field; `503` module disabled or configuration invalid (validation
endpoints only); `404`/`405` unknown route or method.

A validation report contains: `valid`, `rows_total`, `rows_valid`, `error_count`, `warning_count`,
`missing_required_columns`, `unexpected_columns`, `issues` (code, severity, column, 1-based row; **never the cell value**),
`issue_counts` (complete even when `issues` is truncated), `missing_value_counts`, `duplicate_records`,
`invalid_customer_ids`, `invalid_timestamps`, `out_of_order_records`, `unknown_customer_ids`, `persisted` (always `false`).

## 4. Lifecycle proxy: method

Groups customers by `tenure` (months). Thresholds are configurable; the defaults are

| Group | Months (min inclusive, max exclusive) |
|---|---|
| New Customer | 0 - 6 |
| Early Lifecycle | 6 - 12 |
| Developing Customer | 12 - 24 |
| Established Customer | 24 - 48 |
| Long-Term Customer | 48 and above |

These boundaries are a documented **policy choice**, not a finding. Per group the endpoint returns customer count and
share, observed churn (count of `Churn == Yes` among labelled customers; the percentage is **withheld** below
`min_group_size_for_rate`, default 30), contract distribution, and summaries of `MonthlyCharges` and `TotalCharges`.

* Churn figures are the **actual labels** in the dataset, not predictions.
* Charges are billing amounts as recorded (currency unspecified). They are not profit or lifetime value.
* Missing, negative or non-numeric tenure rows are excluded and counted. Blank `TotalCharges` are counted as missing,
  never filled.
* Risk distribution is `BLOCKED_BY_MISSING_DATA` unless existing churn probabilities are supplied, either as a
  `churn_probability` column or through `register_experience(app, settings, probability_provider=callable)`. Bands use the
  policy thresholds in the config; nothing is re-predicted.
* This is a tenure proxy, **not** an event-based journey and not a real-time analytics engine.

## 5. Data schemas for future real datasets

| Dataset | Required columns | Optional |
|---|---|---|
| feedback | `feedback_id`, `customer_id`, `feedback_text`, `submitted_at` | `channel`, `sentiment_label` (human label) |
| tickets | `ticket_id`, `customer_id`, `category`, `severity`, `status`, `created_at` | `resolved_at`, `sla_due_at` |
| nps / csat | `response_id`, `customer_id`, `score`, `survey_date` | |
| events | `customer_id`, `event_type`, `event_timestamp`, `channel` | `event_id`, `metadata` (JSON object) |

Checks: required columns and values, types, allowed categories (severity, status, sentiment label), ISO 8601 timestamps
(not before `min_date`, not in the future), customer-id pattern, duplicates (by id, or by customer+type+timestamp+channel
for events), ticket SLA consistency (`resolved_at` and `sla_due_at` not before `created_at`), survey scores finite and
inside the configured scale, per-customer timestamp ordering (warning; sequences are re-sorted), unknown customer ids
(warning against the customer dataset), spreadsheet-formula prefixes in free text (warning; content is never executed).

Formulas
* NPS = % promoters - % detractors over **valid** responses. Defaults: 0-10 scale, detractor <= 6, promoter >= 9.
* CSAT = satisfied responses / valid responses x 100. Defaults: 1-5 scale, satisfied >= 4.
* Valid = finite, inside the scale, inside the optional period. Missing, out-of-scale and out-of-period responses are
  counted and reported. With zero valid responses the result is BLOCKED, never 0. Below `min_responses` the value is
  returned with `low_sample: true`.

## 6. Configuration (`configs/experience.yaml`)

`enabled`, `limits` (bytes 5 MiB, rows 100,000, columns 50, field 10,000 chars, issues reported 200), `customer_id.pattern`,
`timestamps`, `data_dir`, `datasets` (all `null`), `lifecycle`, `surveys`, `complaints`, `journey`, `sentiment`. The loader
rejects unknown keys, wrong types, non-contiguous lifecycle groups and inconsistent scales. `TRICHURN_EXPERIENCE_CONFIG`
may point to another file. To activate a module: put the real file in `data/experience/` and set its name under
`datasets:`. Changes are picked up without a restart (cache key is path, mtime and size).

## 7. Security

* Content is only parsed (`csv`, `json`, `yaml.safe_load`); nothing is evaluated, imported or executed. NaN/Infinity rejected.
* Size, row, column and field limits; NUL bytes and non-UTF-8 rejected; a `Content-Length` guard returns 413.
* Configured dataset paths must be relative, free of `..`, `.csv`/`.json`, and resolve inside `data_dir` (symlink escapes
  rejected); `data_dir` must be inside the project.
* Uploads are not persisted, not logged and not transmitted anywhere. Reports and errors never echo cell values or server paths.
* No sentiment model is ever loaded from a configured path (pickle/joblib loading would execute code). Models are registered in code only.

## 8. Running

```
pip install -r requirements-phase13.txt            # nothing new if the Phase 6 API already runs
python scripts/verify_phase13_locked_artifacts.py   # must print: all locked artifacts match
uvicorn app.main:app --port 8000                    # backend
cd frontend && npm run dev                          # frontend; open /experience and /experience-lifecycle
```
Set `VITE_API_BASE_URL` (default `http://localhost:8000`). The Experience pages read the backend directly and are
independent of `VITE_DATA_PROVIDER`: if the backend is unreachable they show an error, never mock figures.

Tests
```
pytest tests/unit/test_experience_*.py tests/unit/test_phase13_locked_artifacts.py tests/experience_api
cd frontend && npm run typecheck && npm test && npm run lint && npm run build
```

## 9. Known limitations

* Sentiment, complaint, NPS, CSAT and journey analytics have been exercised only with **synthetic test fixtures**; they have never run on real data.
* No sentiment model exists. Training one needs a labelled feedback dataset and is outside Phase 13.
* The request body is fully read before the size guard can reject it; also set a limit at your reverse proxy.
* Lifecycle thresholds are a policy choice and the groups are descriptive, not causal.
* Experience pages were verified through automated tests and a production build, not by a human visual review.

## 10. Troubleshooting

| Symptom | Cause and fix |
|---|---|
| Pages show "could not be reached" | Backend not running or wrong `VITE_API_BASE_URL`. |
| Everything `VALIDATION_FAILED` with a config message | Fix the named key in `configs/experience.yaml`. |
| Module stays BLOCKED after adding a file | File not inside `data/experience/`, name not under `datasets:`, or file missing. |
| Dataset `VALIDATION_FAILED` | Use `POST /data-quality` with the file to see row-level issues. |
| 413 on upload | Over the configured limit; raise `limits` or split the file. |
