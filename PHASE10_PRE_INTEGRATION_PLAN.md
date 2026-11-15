# Phase 10 Pre-Integration Plan

**Status:** Audit-only. No Phase 10 files have been integrated, and no project or staging files were copied, moved, overwritten, deleted, renamed, or otherwise changed during the audit. This plan is the only file created.

**Decision:** Do not apply the overlay yet. First reconcile the baseline fingerprint, obtain approval for the Git/DVC prerequisites, and correct the Airflow command-construction risk described below. Keep the staging package intact until those items are resolved.

## 1. Scope and existing project

Project root: `C:\Users\ASUS\Downloads\Customer Churn Prediction`

The existing project is Phase 1–9. Its relevant structure includes:

- `app/`, `configs/`, `docs/`, `ml/`, `mlops/`, `models/`, `scripts/`, `tests/`, and `frontend/`.
- Existing API routes, including `app/api/routes/model_lifecycle.py`, and existing settings/configuration.
- Existing model artifacts and sidecars in `models/`.
- Existing DVC-related ignore patterns in the root `.gitignore`; there is no `.dvc/` directory, DVC pipeline, or DVC dataset pointer in the project.
- There is no Git repository metadata at the project root and no `dvc` executable in the current Python environment.

The existing root `scripts/` directory will receive new files, but none of the 11 Phase 10 script names collide with current script names. The staging package has **zero exact relative-path file collisions** with the project. This means the overlay is additive by path, not that it is safe to unzip wholesale: the `.dvc/` state, root DVC files, and existing ignore rules still require controlled integration.

## 2. Phase 10 source structure and responsibilities

The staging folder, `C:\Users\ASUS\Downloads\TriChurn_Phase10_Staging\TriChurn_Phase10_DVC_Airflow`, contains exactly 57 files:

- Root (6): `.dvcignore`, `.env.phase10.example`, `dvc.lock`, `dvc.yaml`, `PHASE10_OVERLAY.md`, `requirements-phase10.txt`.
- `.dvc/` (2): `.dvc/.gitignore`, `.dvc/config`.
- `artifacts/` (1): `artifacts/.gitignore`.
- `configs/` (2): `configs/integrity_manifest.json`, `configs/promotion.yaml`.
- `docs/` (1): `docs/phase10.md`.
- `ml/data/raw/` (1): `ml/data/raw/telco_churn.csv.dvc`.
- `ml/experiments/phase10/` (4): `data_validation.json`, `evaluation.json`, `feature_engineering.json`, `preprocessing.json`.
- `orchestration/` (2): `orchestration/.gitignore`, `orchestration/dags/trichurn_pipeline.py`.
- `pipeline/` (11): `__init__.py`, `cli.py`, `drift_hook.py`, `errors.py`, `fileio.py`, `gate.py`, `integrity.py`, `promotion.py`, `settings.py`, `stages.py`, `status.py`.
- `scripts/` (11): `approve_model.py`, `dvc_remote.py`, `engineer_features.py`, `evaluate.py`, `pipeline_status.py`, `preprocess.py`, `promote_model.py`, `train.py`, `validate_data.py`, `validate_model_artifact.py`, `verify_integrity.py`.
- `tests/phase10/` (9): `__init__.py`, `conftest.py`, `dagbag_probe.py`, `test_airflow_dag.py`, `test_dvc_config.py`, `test_integrity_and_status.py`, `test_model_workflow.py`, `test_phase10_security.py`, `test_pipeline_stages.py`.
- `training/` (2): `training/dvc.yaml`, `training/params.yaml`.
- `verification/` (5): `PHASE10_VERIFICATION.md`, `phase10/BASELINE_P1_8_sha256_pre_phase10.txt`, `phase10/candidate_evaluation.json`, `phase10/candidate_training.json`, `phase10/manual_training_dvc_run.txt`.

The two DVC pipeline files have distinct roles:

- Root `dvc.yaml` is the normal data/integrity pipeline: approved-artifact integrity, data validation, preprocessing, feature engineering, and approved-model evaluation. It declares no model-training stage.
- `training/dvc.yaml` is a separate manual candidate-training/evaluation pipeline. Its candidate artifacts are written under `artifacts/candidates/`, not `models/`; it has explicit training gates and does not itself approve or promote a model.

This separation should be preserved. A normal root `dvc repro` must not become a training or promotion path.

## 3. Baseline, data, and model integrity findings

### Phase 1–8 fingerprint

The supplied fingerprint has 273 normalized entries. Compared with the current project, it has:

- **35 existing paths with different SHA-256 values**.
- **3 paths absent from the current project:** `README_PHASE6.md`, `docs/phase7.md`, and `requirements-phase6.txt`.

The mismatches include Phase 9/retention-facing files as well as other project files. This is not sufficient evidence to classify every difference as an intentional Phase 9 change or as an accidental Phase 1–8 change. The supplied `verification/PHASE10_VERIFICATION.md` assertion of zero changed/deleted files is therefore **not confirmed for this workspace**. Do not restore or overwrite files based only on the fingerprint; first reconcile the three missing paths and 35 differences against the approved Phase 9 baseline and source history.

The existing `TriChurn_Pre_Phase9_Backup_20261110_231500` is not a complete comparator for this fingerprint: 90 manifest paths are absent from that backup and 26 paths present there differ from the fingerprint. Do not overwrite or repurpose that backup. The workspace has no Git history with which to establish a tracked-file baseline.

### Dataset and artifacts

The existing `ml/data/raw/telco_churn.csv` is present and matches the Phase 10 pointer and manifest:

- Size: 970,457 bytes.
- MD5: `3b0bfab28a8101b4e4fdd08025a5c235`.
- SHA-256: `16320c9c1ec72448db59aa0a26a0b95401046bef5d02fd3aeb906448e3055e91`.

No DVC cache object was found in the checked project, staging, or standard user cache locations. Staging `.dvc/config` has no remote configured. The dataset is currently available locally, but DVC cannot restore it if it is later removed unless a cache or remote is made available; the existing `scripts/download_telco.py` is another documented restoration path.

The Phase 10 integrity manifest matches all five current entries (the dataset, two model binaries, and two model sidecars). The locked model SHA-256 values are:

- Phase 2 churn model: `db399a55f650c6681e1caaf52257f909777e2c5fada3af5911370ddf5b8ff1ad`.
- Phase 5 segmentation model: `38423c9cf19b05aa35b72acd44ea3a8af4c3775a1e6cf2bb739ee1972dc05927`.

Their current sidecars also match the Phase 10 manifest. Do not copy or replace the dataset or any model artifact from the overlay; the overlay does not need to supply those binaries.

## 4. File disposition and exact proposed changes

These are recommendations for a later, explicitly approved integration—not actions performed in this audit.

### A. Add after the blockers below are cleared

Add these as new files, preserving all existing files:

- Configuration and environment examples: `.dvcignore`, `.env.phase10.example`, `configs/integrity_manifest.json`, `configs/promotion.yaml`, `requirements-phase10.txt`.
- Phase 10 implementation: all 11 files in `pipeline/` and all 11 listed in `scripts/`.
- Phase 10 tests: all 9 files in `tests/phase10/`; do not edit or replace existing Phase 1–9 tests.
- Orchestration: `orchestration/.gitignore`, and `orchestration/dags/trichurn_pipeline.py` **only after** resolving the Airflow command-templating issue in section 6.
- Runtime ignore rules: `artifacts/.gitignore`.
- Documentation: `docs/phase10.md` and `PHASE10_OVERLAY.md` only after correcting their project-root, Git/DVC, and validation instructions for this Phase 1–9 workspace. Do not follow the overlay document's blanket “unzip over” instructions.

`configs/integrity_manifest.json` was checked against the current dataset, models, and model sidecars. `configs/promotion.yaml` inherits existing optimization criteria, but those criteria must still be reviewed as policy before any real promotion.

`requirements-phase10.txt` should remain a separate, opt-in requirements file. Do not merge it into or replace `requirements.txt`, `requirements-api.txt`, or `requirements-phase8.txt`.

### B. Carefully initialize, merge, or regenerate

| Staging path(s) | Proposed handling |
|---|---|
| `.dvc/config`, `.dvc/.gitignore` | Do not copy this directory over the project. Once Git/DVC setup is separately approved, initialize DVC in the approved repository and merge only the intended non-secret setting (analytics disabled). Keep remote URLs and credentials out of committed config; configure any remote locally. |
| `dvc.yaml` | Add as a new root pipeline only after checking every dependency/output against the Phase 9 tree and exercising it in a disposable copy. In particular, it declares the approved model binaries as persistent DVC outputs; prove DVC cannot remove, rewrite, or relink the real project artifacts before relying on this design. |
| `training/dvc.yaml`, `training/params.yaml` | Add as the separate, manual-only candidate pipeline. Keep its explicit gate and candidate-only output paths; do not merge its stages into root `dvc.yaml`. |
| `ml/data/raw/telco_churn.csv.dvc` | The pointer matches the current CSV, but add it only after approved Git/DVC initialization. Do not rerun `dvc add` against the real models or dataset during integration planning. |
| `dvc.lock` | **Do not copy as the project's final lock.** It is a generated snapshot for the staged code and outputs. Regenerate it only after the final approved source/config layout is in place and the chosen DVC version, dataset, and line endings are verified. No `dvc repro` was run in this audit. |
| Existing root `.gitignore` | Preserve it. It already ignores raw CSV, processed data, and `models/*.joblib`; do not replace it with a staging copy. Inspect any DVC-generated ignore edits as a diff and retain all current Phase 1–9 rules. |

### C. Preserve as staging evidence; do not seed live runtime output paths

Do not copy these pre-generated outputs into the live project during integration:

- `ml/experiments/phase10/data_validation.json`
- `ml/experiments/phase10/evaluation.json`
- `ml/experiments/phase10/feature_engineering.json`
- `ml/experiments/phase10/preprocessing.json`
- `verification/PHASE10_VERIFICATION.md`
- `verification/phase10/BASELINE_P1_8_sha256_pre_phase10.txt`
- `verification/phase10/candidate_evaluation.json`
- `verification/phase10/candidate_training.json`
- `verification/phase10/manual_training_dvc_run.txt`

Keep them intact in staging as evidence. The generated stage reports can cause `pipeline_status.py` to report prior execution state if placed directly in the runtime report directory. The baseline and verification claims also need reconciliation with the current Phase 9 workspace before they are treated as project evidence.

### D. Never overwrite during this integration

Do not overwrite the project's `.env`, root `.gitignore`, any existing `configs/` file, existing API/frontend/routes/providers, Phase 9 files, existing dataset, any of the four files under `models/`, or any model sidecars. Do not copy a staged file over a same-purpose existing Phase 1–9 file simply because the overlay documentation describes itself as additive.

## 5. DVC integration strategy

Prerequisites and compatibility:

1. DVC requires a Git repository context, but this project has no `.git` directory. Do not initialize Git as part of this audit; Git initialization requires separate approval.
2. DVC is absent from the current Python environment. The project already has separate ML, API, and Phase 8 dependency manifests. The overlay's only declared Python addition is `dvc>=3.50`; its documentation reports testing with DVC 3.67.1 on Linux. No dependency resolution or install was attempted.
3. There is no configured DVC remote and no verified cache object in checked locations. The current CSV/pointer match, but remote/cache restoration is not available in the audited workspace.
4. The project `.gitignore` already excludes the raw CSV, processed data, and model binaries. The Phase 10 DVC tests' scratch-project builder does not copy the existing root `.gitignore`, so those tests alone do not prove compatibility with the actual ignore rules.
5. The root DVC pipeline declares the Phase 2 and Phase 5 model binaries as `persist: true` outputs. The package asserts that this preserves them, but the model-output lifecycle has not been validated locally. A staged lock's matching hashes are not a substitute for testing DVC checkout/repro behavior in a disposable copy with the real ignore rules.

Recommended sequence after approval:

- Approve or create the Git repository separately, then initialize DVC rather than copying the staging `.dvc/` directory.
- Decide on an approved DVC version and an optional trusted remote; keep remote details in ignored local configuration. Do not send customer data to an unapproved remote.
- In a disposable copy, verify the dataset pointer, root pipeline, existing ignore rules, and DVC model outputs. Compare all four model/sidecar SHA-256 values and the exact `models/` listing before and after each DVC operation. Do not experiment against the real project.
- Regenerate `dvc.lock` for the reconciled Phase 9 source tree and intended output state. The staged lock is not accepted as authoritative for this workspace.
- Keep training in `training/dvc.yaml`; do not run training or promotion as part of this audit or an ordinary data-pipeline validation.

## 6. Airflow integration strategy and security blocker

The DAG uses project-relative scripts and derives its default root from `orchestration/dags/`; it references scripts included in the overlay, including `scripts/validate_model_artifact.py`. It defines a manual data/evaluation DAG, a separately paused promotion DAG, and a disabled-by-default drift placeholder. It does not import Phase 9 or call a Phase 9 API. No Phase 9 API, route, or service change is required by the inspected DAG.

Airflow is not supported on native Windows. The staging documentation calls for a separate Linux/WSL2/Docker environment. In that environment, explicitly set the project root and `TRICHURN_PYTHON` to paths valid inside the Linux environment; do not assume Windows paths or the Airflow interpreter are the project's ML interpreter.

**Blocking security concern:** the DAG interpolates `dag_run.conf` candidate-version values into `BashOperator` command strings for training and promotion. Candidate validation occurs in the called Python code, after the shell command has already been constructed and started. This creates a shell-injection risk from untrusted DAG-run configuration. Do not install or enable this DAG until command construction no longer places untrusted values in shell text (for example, pass validated values without shell interpolation) and the revised behavior is tested in the supported Airflow environment.

The staged report says the DAG parsed with Airflow 3.4.0, but that is package-supplied evidence and was not independently reproduced on this Windows workspace. Airflow is absent from the current environment.

## 7. Dependencies, tests, and Phase 1–9 preservation

### Dependencies

- Existing manifests: `requirements.txt`, `requirements-api.txt`, and `requirements-phase8.txt` remain untouched.
- Phase 10 adds a separate DVC requirement; no DVC resolver compatibility was checked and no package was installed.
- Airflow is intentionally omitted from the Phase 10 requirements and should stay in a separate constrained environment.
- `.env.phase10.example` is an example, not a replacement for the existing `.env` or Phase 8 `.env.example`. The training, drift, and DVC switches default off in the inspected example.

### Tests

The Phase 10 suite is isolated under the new `tests/phase10/` path and can be added without editing existing tests. It includes static checks and DVC/Airflow integration checks that may skip when those tools are unavailable. Some model-workflow tests execute approval/promotion behavior against temporary fixtures; they were **not run** because the requested task is audit-only and explicitly prohibits training or promotion. No Python, DVC, Airflow, or frontend test suite was run for this audit.

The Phase 10 package's reported test totals and Linux results in `verification/PHASE10_VERIFICATION.md` are not local test results. Do not report them as verified for this project.

### Preservation

- There are no exact path collisions in the 57-file overlay; the additions under existing `scripts/`, `configs/`, and `docs/` do not replace a same-named existing file.
- Keep `app/api/routes/model_lifecycle.py`, all Phase 9 retention routes/services/settings/schemas, frontend routes/providers/services/navigation, and all existing Phase 1–8 model/config/test files unchanged.
- Add tests only under `tests/phase10/`; do not alter an existing regression test to accommodate the overlay.
- Preserve the four model-directory files and their bytes. The local Phase 10 manifest currently matches the two model binaries and both sidecars.
- A baseline preservation pass cannot be certified until the 35 mismatches and three absent fingerprint paths are resolved.

## 8. Backup plan

Create no backup during this audit. Before an approved integration, make a **fresh, complete** backup as a new sibling of the project, for example:

`C:\Users\ASUS\Downloads\TriChurn_Pre_Phase10_Backup_20261111_<unique-HHmmss>`

First verify the exact destination does not exist; choose a new timestamp if it does. Include hidden files and generated data/artifacts, then verify the backup's model SHA-256 values and file inventory. Do not overwrite or reuse `TriChurn_Pre_Phase9_Backup_20261110_231500`, `Customer Churn Prediction_BACKUP`, or `Customer Churn Prediction_PHASE8_BACKUP`.

## 9. Risks and unresolved conflicts

1. **Baseline reconciliation is required:** 35 hashes differ and three manifest paths are absent in the current project; the pre-Phase-9 backup is incomplete for a full comparison.
2. **DVC is not currently usable here:** no Git repository, no DVC executable, no configured remote, and no discovered cache object.
3. **Dataset recovery is not guaranteed by DVC:** the CSV exists and matches the pointer, but the pointer does not supply the missing cache or remote.
4. **Approved-model DVC outputs are not validated against this project's ignore rules:** test fixtures omit the existing root `.gitignore`; real artifacts must only be exercised in a disposable copy.
5. **Staged `dvc.lock` is not authoritative** for a Phase 9 tree whose source fingerprint differs; Windows line-ending changes can also cause dependency hashes to be recalculated.
6. **Airflow command interpolation is a security blocker** and must be fixed before DAG deployment.
7. **Dependency compatibility is unverified:** DVC was not installed or resolved; Airflow must remain isolated.
8. **Training/evaluation limitations:** the pipeline is not a causal uplift model. Candidate eligibility uses stored single-shot TEST metrics, which becomes test-set selection if many candidates are compared. The criteria are inherited project thresholds and must be reviewed before a real promotion. Training, approval, and promotion are outside this audit and were not performed.
9. **Package evidence is not current-workspace validation:** staged Linux test/build/DVC/Airflow claims were not reproduced here and the baseline assertion conflicts with this workspace's direct hash comparison.

## 10. Exact next actions after approval

1. Reconcile all 35 fingerprint mismatches and three missing paths against the approved Phase 9 baseline; document which differences are intentional before accepting a new Phase 10 baseline.
2. Approve a fresh backup destination and verify it is unused; create and hash-verify the backup.
3. Separately approve Git/DVC repository setup and dependency isolation. Do not initialize Git or install dependencies without that approval.
4. Correct and test the Airflow command handling before adding/enabling the DAG.
5. Add the source/config/test files listed in section 4A, preserving existing Phase 1–9 files and manifests.
6. Initialize DVC in the approved Git repository; carefully add the DVC configuration, pipeline files, and matching dataset pointer from section 4B.
7. Validate DVC behavior only in a disposable copy first, including existing `.gitignore` rules and preservation of the Phase 2/5 model and sidecar hashes. Regenerate `dvc.lock` for the final reconciled tree.
8. Add no staged reports to runtime output paths; run only the explicitly approved, non-training validation checks and report exact observed results.

**Current outcome:** audit and plan only. No integration, model training, model promotion, dependency installation, Git initialization, or push was performed. Awaiting approval before any next action.
