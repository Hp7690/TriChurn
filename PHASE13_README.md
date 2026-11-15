# TriChurn Phase 13: Customer Experience & Sentiment Intelligence (overlay)

An **additive** overlay for the existing TriChurn project. It does not replace, rename or delete anything, does not touch
the locked Phase 2 / Phase 5 models, and adds no dependency.

## What it does today
* **Tenure-based lifecycle proxy** on the existing Telco data: customer counts, observed churn, contract mix and charge
  summaries per tenure group. Clearly labelled a proxy, not an event-based journey.
* **Validation framework** for feedback, ticket, NPS, CSAT and journey-event files (CSV or JSON), in memory only.
* **Experience Command Center** (`/experience`) and **Lifecycle** page (`/experience-lifecycle`).

## What stays blocked until real data exists
Sentiment, complaint intelligence, NPS, CSAT and journey analytics return `BLOCKED_BY_MISSING_DATA` with no figures. The
Telco dataset has no feedback text, tickets, survey scores or event timestamps, and nothing is inferred from churn or
`TechSupport`. The formulas, validators and aggregators are built and tested (with synthetic fixtures) and activate when
you configure real files in `configs/experience.yaml`.

## Quick start
1. Read `PHASE13_INTEGRATION_GUIDE.md` (dry run first: `python scripts/integrate_phase13.py --project-root <your project>`).
2. `python scripts/verify_phase13_locked_artifacts.py`
3. Run the backend and frontend as in `docs/phase13.md` section 8.

## Documents
| File | Contents |
|---|---|
| `docs/phase13.md` | Full reference: architecture, API, schemas, formulas, configuration, security, limitations |
| `PHASE13_INTEGRATION_GUIDE.md` | How to merge into your current project without overwriting Phases 1-12 |
| `PHASE13_VERIFICATION.md` | Exact test results, regression comparison, hash verification, what was not verified |
| `PHASE13_CHANGELOG.md` | New files and the four patched files |
