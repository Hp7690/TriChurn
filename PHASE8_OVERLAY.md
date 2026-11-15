# TriChurn Phase 8 overlay - how to merge

This archive is an **overlay**: unzip it over the approved Phase 1-7 project root (the folder that contains `app/`, `ml/`,
`models/`, `frontend/`). It adds 31 new files (code, tests, docs, config examples, evidence) and replaces exactly ONE existing file, `app/main.py` (2 lines: import +
`include_router` of the new read-only lifecycle endpoint). It contains no models, datasets, caches or secrets.

    pip install -r requirements-phase8.txt        # adds only: mlflow>=3.17
    python scripts/run_phase8_registry.py verify  # then: register | status | fetch --dest DIR
    pytest tests/phase8 -q ; ruff check .

Full documentation: `docs/phase8.md`. Evidence: `verification/PHASE8_VERIFICATION.md`.
