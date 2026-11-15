# Phase 13 integration guide

**Read first.** This overlay was built and tested against the *Phase 1-7 handoff snapshot*, not against your current
Phase 9 project. Everything marked "verify locally" below is unproven on your tree. The script never guesses: if a file
differs from what it expects it stops and tells you the exact manual edit.

## What gets touched
* **New files only** (see `PHASE13_CHANGELOG.md`). A new file that already exists with different content is a CONFLICT and aborts everything.
* **Four existing files, additive edits only**, each backed up first as `<file>.phase13.bak`:

| File | Edit |
|---|---|
| `app/main.py` | `from app.api.routes.experience import register_experience` and `register_experience(app, settings)` before `return app` in `create_app()` |
| `frontend/src/App.tsx` | imports of `ExperiencePage`, `LifecyclePage`; routes `experience` and `experience-lifecycle` before the catch-all |
| `frontend/src/components/Sidebar.tsx` | `import { EXPERIENCE_NAV } from './experienceNav'` and `...EXPERIENCE_NAV,` in the `NAV` array |
| `frontend/src/services/api/contract.ts` | `export { EXPERIENCE_ENDPOINTS } from './experienceContract';` |

Not touched: `models/`, `ml/`, other `configs/`, `requirements.txt`, existing tests, Phase 9 files, any dependency.
Routes are `experience` and `experience-lifecycle` (not `experience/lifecycle`) because the sidebar's `NavLink` would
otherwise highlight both entries. If either name collides with a Phase 9 route, the script reports a CONFLICT and stops.

## Steps
1. **Back up** your project folder (copy it, or commit to git).
2. Unzip this package somewhere *outside* the project.
3. **Dry run** (changes nothing):
   ```
   python scripts/integrate_phase13.py --project-root "C:\path\to\Customer Churn Prediction"
   ```
   Expected: `0 CONFLICT(S)` and four `WILL-APPLY` lines. Any `MANUAL` or `CONFLICT` line includes the exact edit to make.
4. **Apply**:
   ```
   python scripts/integrate_phase13.py --project-root "C:\path\to\Customer Churn Prediction" --apply
   ```
   Exit 0 = done; 1 = conflict (nothing changed); 2 = copied, but a manual edit is still needed. The script prints the
   locked-model hash check before and after.
5. Verify:
   ```
   python scripts/verify_phase13_locked_artifacts.py
   pytest tests/unit/test_experience_*.py tests/unit/test_phase13_locked_artifacts.py tests/experience_api
   pytest                                   # your full existing suite
   cd frontend && npm run typecheck && npm test && npm run lint && npm run build
   ```
6. Start the backend and frontend and open `/experience` (see `docs/phase13.md` section 8).

## Verify locally (not proven on your Phase 9 tree)
* The four patches apply (dry run tells you). Phase 9 may already have edited the same four files.
* No route or nav collision with Phase 9 or the staged Phase 10.
* The project's architecture test (`tests/unit/test_phase6_architecture.py`) still passes. It did on the snapshot; it is why the domain package is `trichurn_experience/` and not `ml/experience/`.
* If your `tests/support/` exists, run the **whole** suite: it was not available on the snapshot, so existing `tests/api` was never run by me.

## Rollback
1. Restore each patched file from its `.phase13.bak`.
2. Delete the new files listed in `PHASE13_CHANGELOG.md`.
No data, model or database is modified by Phase 13, so nothing else needs undoing.

## Phases 10, 11, 12
Phase 13 depends on none of them and assumes none is integrated. It does not use Phase 9 either; the optional
`probability_provider` hook is the only seam where Phase 9 (or any source of churn probabilities) can feed the lifecycle
risk distribution:
```python
register_experience(app, settings, probability_provider=lambda: {"7590-VHVEG": 0.81, ...})
```
