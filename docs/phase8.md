# Phase 8 - Productionization: MLflow Experiment Tracking, Model Registry & Artifact Integrity

Status: see "Tests executed" for the exact verified numbers. Phases 1-7 are frozen; this phase only **adds** a tracking /
registry / integrity layer around the **existing** Phase 2 model. Nothing is retrained, replaced or re-tuned.

## 1. Objective
Make the existing, locked churn model (`models/trichurn_churn_model_v2.0.0.joblib`, version 2.0.0) more production-ready:
track it in MLflow, register it in the MLflow Model Registry as the production candidate, and verify its integrity
(SHA-256 + version) before it is ever loaded. The model file stays the single source of truth.

## 2. Architecture
```
 MLflow registry (optional, offline-safe)      scripts/run_phase8_registry.py  {verify|register|status|fetch}
        |  fetch_verified_model()                     |
        v                                             v
  model artifact on disk  --->  mlops.integrity  (bytes -> SHA-256 -> pinned digest -> sidecar cross-check -> version)
                                      | verified ONLY
                                      v
            mlops.loading.load_verified_model  ->  ml.explainability.load_verified_artifact  (existing Phase 3 loader)
                                      v
             Phase 6 FastAPI (unchanged prediction path)  ->  Phase 7 React frontend (unchanged)
```
* `mlops/` is a NEW top-level package. It is deliberately **not** called `mlflow` (that would shadow the real library).
* Importing `mlops` never imports `mlflow` or the ML stack; they are loaded lazily by the functions that need them.
* Ordinary prediction never touches MLflow and needs no network.

| Module | Role |
|---|---|
| `mlops/config.py` | `MlopsSettings.from_env()` - environment variables, safe defaults, validation (no secrets) |
| `mlops/integrity.py` | stdlib-only verification: `verify_model_artifact` (report) / `require_verified` (raises) |
| `mlops/tracking.py` | `log_model_run`: verify -> log params/metrics/tags -> log artifact -> re-verify (source and stored copy) |
| `mlops/registry.py` | `register_verified_model`, `fetch_verified_model`, `registry_snapshot` |
| `mlops/loading.py` | `load_verified_model`: digest check BEFORE any unpickling, then the existing loader |
| `mlops/status.py` | read-only status (integrity + registry) with a registry timeout; never raises |
| `app/{schemas,services,api/routes}/model_lifecycle.py` | additive read-only endpoint `GET /api/v1/model/lifecycle` |
| `scripts/run_phase8_registry.py` | CLI |

## 3. MLflow setup
Default: a **local SQLite store** under `./mlflow_local/` (created on first `register`; git-ignored by its own
`.gitignore`). No server is needed. (MLflow's plain file store is deprecated in MLflow 3, and the registry needs a database.)
Optional UI / server:
```bash
mlflow server --backend-store-uri sqlite:///mlflow_local/mlflow.db --default-artifact-root ./mlflow_local/artifacts --port 5000
export MLFLOW_TRACKING_URI=http://localhost:5000          # PowerShell: $env:MLFLOW_TRACKING_URI="http://localhost:5000"
```

## 4. Experiment tracking
Experiment: `TriChurn-Churn-Prediction` (created with an explicit artifact location, never an implicit `./mlruns`).
One run per distinct artifact digest (re-running is idempotent; `--force` logs an extra run).

**Metrics** (`roc_auc, pr_auc, brier_score, log_loss, accuracy, precision, recall, f1`) are **read** from the artifact's
own sidecar (`metrics.test` - the single held-out final evaluation Phase 2 already performed). They are not recomputed,
so the TEST split is not read again. They equal the specification baseline to 4 decimals (0.8492 / 0.6412 / 0.1355 /
0.4107 / 0.7711 / 0.5503 / 0.7429 / 0.6322); a test enforces this.

**Params** are only facts present in the sidecar: model_name (`logistic_regression`), model_version, threshold (0.34) +
metric/source, random_state (42), feature_count (19) / model_feature_count (58), target, positive_class,
imbalance_strategy, calibration_method, dataset_version (`sha256:16320c9c1ec7`), dataset_rows (7043), split sizes,
`hp_*` (solver/C/max_iter) and `train_env_*` (library versions recorded at training time). Absent facts are omitted,
not defaulted; a test asserts no invented keys (no learning rate, epochs, ...).

**Tags**: `project=TriChurn, phase=8, model_version=2.0.0, model_type=churn_prediction, status=production,
artifact_sha256, metrics_split=test, metrics_source=phase2_artifact_sidecar, integrity_verified_before/after`.

**Artifacts**: `model/trichurn_churn_model_v2.0.0.joblib` and its `.metadata.json`. The digest is verified before logging,
after logging (source unchanged) and on the stored copy (byte-identical). The original file is never rewritten.

## 5. Model Registry
Registered model `TriChurn-Churn-Model`. MLflow numbers versions itself (`1, 2, ...`); the semantic version is kept in the
version tag `model_version=2.0.0`. Version tags: `project, phase, model_version, model_type, status=production,
artifact_sha256`. The **alias `production`** points at the verified version (MLflow 3 deprecates registry *stages*).
Registration is idempotent (same digest -> same version). A model that does not match the pinned digest, or whose stored
copy was altered, is **never registered or promoted**; there is no automatic promotion of a new model.

## 6. Model versioning
`MLFLOW_MODEL_VERSION` (default `2.0.0`) is checked against the sidecar's `model_version`; a mismatch is an integrity
failure (`version_mismatch`). Promoting a future model means: new artifact + new pinned digest + new version, registered
explicitly through the same verified path.

## 7. SHA-256 / integrity verification
`verify_model_artifact(path, expected_sha256, metadata_path=, expected_version=)` returns an `IntegrityReport`
(`ok, reason, expected/actual sha, expected/actual version, artifact NAME`). Reasons: `missing, unreadable,
sha256_mismatch, metadata_sha256_mismatch, version_mismatch, metadata_unreadable, invalid_expected_sha256, load_failed`.
`require_verified` raises `ModelIntegrityError(name, reason)`; messages carry the file **name** and reason, never a path.
Order: bytes -> digest -> pinned digest -> sidecar -> only then `joblib` (the model is never unpickled unverified).
The digest pin cannot be switched off (`TRICHURN_MODEL_SHA256` must be 64 hex chars).

## 8. FastAPI integration
All Phase 6 endpoints are unchanged (`/health, /liveness, /readiness, /predict, /explain, /business, /segment,
/customer-intelligence`). **One additive endpoint**: `GET /api/v1/model/lifecycle` ->
`{status: verified|integrity_failed|model_missing|misconfigured, model_version, integrity{...}, registry{...}}`, always HTTP
200 (it reports; `/readiness` remains the probe). `registry.status` is `not_configured` unless `MLFLOW_TRACKING_URI` is set;
when set it is queried with a 3 s timeout and any failure becomes `unavailable` / `mlflow_not_installed` /
`not_registered` / `registered`. **If MLflow is down or absent, prediction is unaffected** (Phase 6 already pins and
verifies the Phase 2/5 digests itself and answers 503 when they do not match).
The only edit to an existing file is `app/main.py` (2 lines: import + include of the new router).

## 9. Configuration (`.env.example`)
| Variable | Default |
|---|---|
| `MLFLOW_TRACKING_URI` | local SQLite store under `./mlflow_local/` |
| `MLFLOW_ARTIFACT_LOCATION` | `./mlflow_local/artifacts` (used when the experiment is created) |
| `MLFLOW_EXPERIMENT_NAME` | `TriChurn-Churn-Prediction` |
| `MLFLOW_MODEL_NAME` | `TriChurn-Churn-Model` |
| `MLFLOW_MODEL_VERSION` | `2.0.0` |
| `TRICHURN_MODEL_PATH` | `models/trichurn_churn_model_v2.0.0.joblib` (relative -> project root, never the CWD) |
| `TRICHURN_MODEL_SHA256` | the locked Phase 2 digest `db399a55...ff1ad` |

No credentials are read, stored or logged. Malformed values raise `MlopsConfigurationError` without echoing the value.

## 10. Local setup
```bash
pip install -r requirements.txt -r requirements-phase6.txt -r requirements-phase8.txt   # Phase 8 adds only: mlflow>=3.17
python scripts/download_telco.py                    # real dataset (git-ignored), needed by the Phase 1-5 tests
python scripts/run_phase8_registry.py verify        # integrity only (offline)
python scripts/run_phase8_registry.py register      # log run + register + alias 'production' (idempotent)
python scripts/run_phase8_registry.py status        # integrity + registry state
python scripts/run_phase8_registry.py fetch --dest ./restored   # download 'production' and verify it
uvicorn app.main:app --reload                       # unchanged Phase 6 startup; see GET /api/v1/model/lifecycle
pytest -q ; ruff check .
```
Exit codes of the CLI: 0 ok, 2 integrity failure, 3 MLflow failure, 4 configuration error.
To use a single install command, append the line `mlflow>=3.17` to `requirements.txt` (not done automatically: that file
belongs to Phase 1 and is left byte-identical).

## 11. Tests executed
Environment: Linux, Python 3.12.3, MLflow 3.17.2, scikit-learn 1.8.0, Node 22.22.2. Every number below was produced by
actually running the command.

| Command | Result |
|---|---|
| Baseline, merged Phase 1-7 tree BEFORE any Phase 8 change: `python -m pytest` | **822 passed**, 0 failed, 0 skipped |
| Phase 8 targeted + integration: `pytest tests/phase8` | **97 passed** (integrity 18, mlflow 22, registry 15, model loading 17, API/lifecycle 10, architecture 9, locked artifacts 6) |
| Existing Phase 6 tests (`tests/api`, `tests/unit/test_phase6_*`) | passed inside the full run (159 tests, incl. real HTTP-layer integration) |
| Full regression: `python -m pytest -rs` | **919 passed, 0 failed, 0 skipped**, 2 warnings (7 min 25 s) = 663 (Phase 1-5) + 159 (Phase 6) + 97 (Phase 8) |
| `ruff check .` | All checks passed |
| `npm install` | ok (385 packages) |
| `npm run typecheck` | pass |
| `npm run build` | pass (2290 modules) |
| `npm run lint` | pass (exit code 0) |
| `npm test` | **40 passed, 1 failed** - pre-existing, identical on the untouched Phase 7 zip (see section 14) |
| CLI end-to-end (`verify`/`register` x2/`status`/`fetch`/tamper/wrong pin/bad config) | `verification/phase8_cli_transcript.txt` |

Warnings in the full run (2): Starlette's `httpx` TestClient deprecation (Phase 6, pre-existing) and MLflow's own SQLAlchemy
`noload` deprecation. Neither is suppressed.

Integrity of Phase 1-7 (fingerprint of 242 files taken before Phase 8, `verification/BASELINE_P1_7_sha256_pre_phase8.txt`):
**0 files deleted, 1 changed (`app/main.py`, +2 lines), 27 added**. `models/` still holds exactly the 4 locked files; Phase 2
SHA-256 `db399a55f650c6681e1caaf52257f909777e2c5fada3af5911370ddf5b8ff1ad` and Phase 5 SHA-256
`38423c9cf19b05aa35b72acd44ea3a8af4c3775a1e6cf2bb739ee1972dc05927` verified unchanged. The 81 frontend source files are
byte-identical to the Phase 7 zip. No dataset, `.venv`, `node_modules`, cache or MLflow store is part of the delivery.

## 12. Troubleshooting
* `INTEGRITY FAILURE ... sha256_mismatch` - the model file differs from the pinned digest. Restore the locked artifact
  (never update the pin to match an unexpected file).
* `MLFLOW ERROR: mlflow is not installed` - `pip install -r requirements-phase8.txt`.
* `unavailable` registry status - the tracking server is unreachable; prediction is unaffected. Check `MLFLOW_TRACKING_URI`.
* A tracking URI to a database in a folder that does not exist: MLflow creates missing parent folders; a server URI that
  nothing listens on fails with `MLFLOW ERROR` after MLflow's own retries (tune `MLFLOW_HTTP_REQUEST_MAX_RETRIES`).
* Windows: use `$env:NAME="value"`; the default SQLite URI is built as `sqlite:///C:/.../mlflow_local/mlflow.db`.

## 13. Phase 1-7 compatibility
* Files changed: **`app/main.py` only** (2 lines). Everything else is added. Frontend (Phase 7), models, configs, Phase 1-5
  code and tests are byte-identical to the approved baseline (fingerprint comparison, see "Tests executed").
* Locked digests: Phase 2 `db399a55...8ff1ad`, Phase 5 `38423c9c...05927` - unchanged. No model was trained or regenerated.
* Baseline observed when the three approved zips are merged: **822 tests** (663 Phase 1-5 + 159 Phase 6) pass; the 833 quoted
  in the Phase 8 brief could not be reproduced from the supplied zips (Phase 6's own docs state 139 pass + 20 skipped
  without the project = 159 tests).
* The frontend is not wired to the lifecycle endpoint (Phase 7 is frozen); the endpoint is for operators/probes.

## 14. Known limitations
* The registry stores the raw verified `.joblib` (+ sidecar) as an **artifact registry**; it is not an MLflow `pyfunc`
  flavour, so `mlflow.pyfunc.load_model` is not supported. Loading goes through `mlops.loading` / `fetch_verified_model`.
* Tracked metrics are the stored Phase 2 TEST metrics (historical facts about the locked model), not new measurements.
* Verified on Linux / Python 3.12.3 / MLflow 3.17.2 / scikit-learn 1.8.0 (the version the artifacts were saved with). Not
  run on Windows here; the Phase 1-5 test failures reported on the maintainer's Windows machine are independent of Phase 8.
* The local SQLite store is single-user; use an MLflow server for shared use. MLflow brings a large dependency tree and
  emits one SQLAlchemy deprecation warning (its own code).
* The registry query in the status endpoint uses a thread timeout; a hung network call is abandoned, not killed.
* Frontend: `npm test` shows 1 failing test (`what-if page ... runs a scenario`) - it fails identically on the untouched
  Phase 7 zip in this environment (Phase 7 ships no `package-lock.json`, so dependency versions float). Not caused by or
  fixed in Phase 8 (frozen). Typecheck, build and lint pass.

## Security considerations
No secrets/credentials/tokens in code, config examples or the ZIP; error messages and API responses contain artifact names
and reason codes only (tests assert no paths/tracebacks leak); the model is never unpickled before its digest matches the
pin; the pin cannot be disabled; static tests forbid fit/dump/write/unlink calls in Phase 8 code; the API package never
imports MLflow; no new network calls happen on the prediction path; the optional registry query is opt-in and time-boxed.

## Rollback / disable
Phase 8 is additive. To disable: remove the two `model_lifecycle` lines from `app/main.py` and delete `mlops/`,
`mlflow_local/`, `scripts/run_phase8_registry.py`, `tests/phase8/`, the three `model_lifecycle.py` files, `.env.example`,
`requirements-phase8.txt` and this document. Phase 1-7 behaviour is identical to before.
