# Phase 13 changelog

## Added (all new files; none overwrites an existing file)
```
PHASE13_CHANGELOG.md
PHASE13_INTEGRATION_GUIDE.md
PHASE13_README.md
PHASE13_VERIFICATION.md
app/api/routes/experience.py
app/schemas/experience.py
app/services/experience_service.py
configs/experience.yaml
data/experience/README.md
docs/phase13.md
frontend/src/__tests__/experience.test.tsx
frontend/src/__tests__/experienceFixtures.ts
frontend/src/charts/LifecycleCharts.tsx
frontend/src/components/ExperienceStatusBadge.tsx
frontend/src/components/experienceNav.ts
frontend/src/pages/ExperiencePage.tsx
frontend/src/pages/LifecyclePage.tsx
frontend/src/services/api/experienceContract.ts
frontend/src/services/experienceService.ts
frontend/src/types/experience.ts
requirements-phase13.txt
scripts/integrate_phase13.py
scripts/verify_phase13_locked_artifacts.py
tests/experience_api/__init__.py
tests/experience_api/conftest.py
tests/experience_api/test_experience_api.py
tests/experience_api/test_experience_integration.py
tests/unit/test_experience_config.py
tests/unit/test_experience_foundations.py
tests/unit/test_experience_lifecycle.py
tests/unit/test_experience_surveys.py
tests/unit/test_experience_validation.py
tests/unit/test_phase13_locked_artifacts.py
trichurn_experience/__init__.py
trichurn_experience/complaints.py
trichurn_experience/config.py
trichurn_experience/journey.py
trichurn_experience/lifecycle.py
trichurn_experience/requirements.py
trichurn_experience/schemas.py
trichurn_experience/sentiment.py
trichurn_experience/surveys.py
trichurn_experience/validation.py
```

## Modified (four existing files, additive, backed up as `*.phase13.bak`)
* `app/main.py`: 2 lines (import, `register_experience(app, settings)`)
* `frontend/src/App.tsx`: 4 lines (2 imports, 2 routes)
* `frontend/src/components/Sidebar.tsx`: 2 lines (import, `...EXPERIENCE_NAV`)
* `frontend/src/services/api/contract.ts`: 1 line (re-export)

## New API endpoints (`/api/v1/experience`)
`GET availability, lifecycle, sentiment/status, complaints/status, nps/status, csat/status, journey/status`;
`POST validate-feedback, validate-tickets, validate-survey, validate-events, data-quality`.

## New frontend routes
`/experience` (Experience Command Center), `/experience-lifecycle` (Lifecycle).

## Design decisions
* Domain package is `trichurn_experience/`, not `ml/experience/`, to satisfy the project's architecture test (see `docs/phase13.md` section 2).
* Tests live in `tests/experience_api/` (not `tests/api/`) because the host `tests/api/conftest.py` imports `tests.support`, which is absent from the snapshot. Frontend tests live in `frontend/src/__tests__/` because that is where Vitest looks.
* Lifecycle route is `experience-lifecycle` so the sidebar highlights one entry at a time.

## Not changed
Locked Phase 2/5 models and sidecars, `ml/`, other configs, `requirements.txt`, all existing tests, all existing endpoints and routes.
