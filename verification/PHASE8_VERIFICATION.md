# Phase 8 verification evidence (MLflow tracking, Model Registry, artifact integrity)

Environment: Linux, Python 3.12.3, MLflow 3.17.2, scikit-learn 1.8.0, Node 22.22.2. Everything below was executed.

| Check | Result |
|---|---|
| Baseline (merged Phase 1-7 tree, before Phase 8) `pytest` | 822 passed, 0 failed, 0 skipped |
| `pytest tests/phase8` | 97 passed |
| Full `pytest -rs` (after Phase 8) | 919 passed, 0 failed, 0 skipped, 2 warnings |
| `ruff check .` | clean |
| Frontend `typecheck` / `build` / `lint` | pass / pass / pass |
| Frontend `npm test` | 40 passed, 1 FAILED - pre-existing: identical on the untouched Phase 7 zip; frontend sources byte-identical (81 files) |
| Phase 2 SHA-256 | expected = actual = db399a55f650c6681e1caaf52257f909777e2c5fada3af5911370ddf5b8ff1ad |
| Phase 5 SHA-256 | expected = actual = 38423c9cf19b05aa35b72acd44ea3a8af4c3775a1e6cf2bb739ee1972dc05927 |
| Phase 1-7 files vs pre-Phase-8 fingerprint (242 files) | 0 deleted, 1 changed (`app/main.py`, +2 lines), 27 added |

Files in this folder: `phase8_cli_transcript.txt` (real CLI run: register twice = idempotent, status, fetch, tampered model,
wrong pin, bad config -> exit codes 0/0/0/0/0/2/2/2/4) and `BASELINE_P1_7_sha256_pre_phase8.txt` (the fingerprint taken before
any Phase 8 change).

Open items (not hidden): (1) 1 frontend test fails, pre-existing/not caused by Phase 8 (Phase 7 ships no lockfile); (2) the
brief quotes 833 passing tests for Phase 6 - the supplied zips merge to 822 (663 + 159), consistent with Phase 6's own docs;
(3) verified on Linux only; the Windows failures reported earlier for Phase 1-5 are independent of this phase.
