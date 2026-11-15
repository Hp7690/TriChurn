# Phase 10 Blocker Resolution Plan

**Status:** Read-only follow-up audit. No source, configuration, dependency, Git, DVC, model, or data files were changed. No dependencies were installed; Git was not initialized; no DVC reproduction, training, approval, or promotion was run. This document is the only file created by this investigation.

**Decision:** The original pre-integration blockers are now better classified, but integration is still **not approved or ready to run**. In particular, three baseline paths remain unexplained, two files have no snapshot comparator, the current tree has no authoritative whole-project Phase 9 checksum/commit, and the Airflow DAG needs a code fix before deployment.

## 1. Evidence labels and sources

- **Verified** means directly observed in the current project, Phase 10 staging tree, a recorded Phase 9 file, or official package/vendor documentation retrieved during this audit.
- **Documented** means explicitly stated by the Phase 9 changelog, test report, baseline-diff record, or manifest. It is useful provenance, but not an independently replayed Git diff.
- **Assumption / unresolved** means the available files do not establish authorship, exact timing, or intent. Do not treat it as a verified Phase 9 change or restore it automatically.

Relevant local evidence:

- The Phase 10 fingerprint: `TriChurn_Phase10_DVC_Airflow\verification\phase10\BASELINE_P1_8_sha256_pre_phase10.txt`.
- Phase 9 records: `PHASE9_BASELINE_DIFF.txt`, `PHASE9_CHANGELOG.md`, `PHASE9_MANIFEST.txt`, and `PHASE9_TEST_REPORT.md`.
- The existing snapshot `C:\Users\ASUS\Downloads\TriChurn_Pre_Phase9_Backup_20261110_231500`.
- The older `Customer Churn Prediction_PHASE8_BACKUP`.

The Phase 10 fingerprint contains 273 entries. Normalizing its `./` prefixes and comparing each entry to the current project yields **35 existing paths with different SHA-256 values and 3 paths absent**. These figures are verified. The categories below explain the evidence for each mismatch without claiming more provenance than the records support.

## 2. Accounting for all 35 hash mismatches

### A. Phase 9 frontend integration wiring — 3 paths

| Path | Evidence and explanation |
|---|---|
| `frontend/src/App.tsx` | Current SHA-256 equals the Phase 9 “after” hash in `PHASE9_BASELINE_DIFF.txt`; the route addition is documented Phase 9 integration work. |
| `frontend/src/components/Sidebar.tsx` | Current SHA-256 equals the recorded Phase 9 “after” hash; the retention navigation item is documented Phase 9 work. |
| `frontend/src/main.tsx` | Current SHA-256 equals the recorded Phase 9 “after” hash; the retention provider wiring is documented Phase 9 work. |

### B. Phase 9 reconstructed documentation — 1 path

| Path | Evidence and explanation |
|---|---|
| `docs/phase6.md` | The current SHA-256 matches `PHASE9_MANIFEST.txt`. `PHASE9_CHANGELOG.md` explicitly calls this a reconstructed Phase 6 document. This is a documented Phase 9 deliverable, not evidence that Phase 9 deleted it. |

### C. Phase 9 audit fixes — 3 paths

| Path | Evidence and explanation |
|---|---|
| `app/main.py` | The current SHA-256 is `0b6c186a74be0c11231d5376d4dc9d8dbbab0a2ecdf58bf22b486a392d6e2e18`, not the original Phase 9 package hash `120488bb9e3e944860f5c06c4049973f9ce2679cc7f9bf41d74f99e019d54a0b`. A read-only comparison against the actual `TriChurn_Phase9_Retention_Intelligence.zip` entry shows the current file retains the Phase 9 retention wiring and adds the existing `model_lifecycle` route import/registration omitted from the package version. `PHASE9_TEST_REPORT.md` records that the pre-existing lifecycle route must remain preserved and that its regression assertion was updated. This hash difference is an intentional compatibility correction, not an unexplained modification. |
| `frontend/src/components/Card.tsx` | `PHASE9_TEST_REPORT.md` records that the Card header was changed so description-only cards render their description. Its current file timestamp is after the 23:15 pre-Phase-9 snapshot, and its hash differs from that snapshot. This is a documented audit fix. |
| `tests/phase8/test_api_lifecycle.py` | The Phase 9 test report records changing the route-set assertion to preserve the existing routes while allowing the additive retention routes. Its current timestamp is after the pre-Phase-9 snapshot. This is a documented Phase 9 compatibility-test adjustment. |

### D. Earlier, identifiable user-requested fixes — 10 paths

These are not Phase 9 integration changes. The conversation history and existing code identify the intent for all ten. The nine frontend files match the pre-Phase-9 snapshot. `scripts/run_phase5.py` is not present in that backup, so its attribution rests on the earlier recorded Windows encoding fix and its timestamp, not on that snapshot.

| Paths | Evidence and explanation |
|---|---|
| `frontend/src/services/adapters/FastAPIDataProvider.ts`, `frontend/src/pages/CustomersPage.tsx`, `frontend/src/utils/segments.ts`, `frontend/src/pages/WhatIfPage.tsx`, `frontend/src/services/aggregations.ts`, `frontend/src/pages/InsightsPage.tsx`, `frontend/src/utils/format.ts`, `frontend/src/__tests__/provider.test.ts`, `frontend/src/__tests__/pages.test.tsx` | Earlier requested frontend fixes for live scoring/loading, customer risk counts, segment labels, What-if CLV step validation, and insights expected-benefit rounding. The previous task record identifies these source/test files. |
| `scripts/run_phase5.py` | Earlier Windows test work addressed console encoding of the rupee symbol. The file predates the Phase 9 audit by timestamp. This is separate from the Phase 9 overlay. |

### E. Pre-Phase-9 snapshot divergence with no complete change record — 16 paths

The current hashes of these paths match the pre-Phase-9 backup, so the differences from the Phase 10 P1–8 fingerprint **already existed by that snapshot**. The Phase 9 changelog does not list them as Phase 9 modifications. Available evidence does not establish which earlier phase/task introduced each difference; they cannot be labeled Phase 9 audit edits, but they are not new changes made during this follow-up audit.

- `frontend/package.json`
- `frontend/src/charts/ActionBenefitChart.tsx`
- `frontend/src/charts/ValueAtRiskChart.tsx`
- `frontend/src/components/CustomerTable.tsx`
- `frontend/src/components/RetentionActionCard.tsx`
- `frontend/src/data/businessMath.ts`
- `frontend/src/pages/CustomerDetailPage.tsx`
- `frontend/src/pages/DashboardPage.tsx`
- `frontend/src/pages/SegmentsPage.tsx`
- `frontend/src/services/api/contract.ts`
- `frontend/src/types/index.ts`
- `tests/integration/test_segmentation_real_data.py`
- `tests/phase8/test_registry.py`
- `tests/support/__init__.py`
- `tests/unit/test_final_evaluation_serialization.py`
- `tests/unit/test_phase2_test_isolation.py`

The Phase 9 changelog says `frontend/package.json` and its lockfile were unchanged during that integration. That statement is consistent with the pre-Phase-9 snapshot, but does not explain the earlier difference from the Phase 10 fingerprint.

### F. Two unresolved historical mismatches

| Path | Verified evidence | Unresolved point |
|---|---|---|
| `mlops/config.py` | Current file differs from the Phase 10 fingerprint and has a 2026-11-05 timestamp. It is absent from the checked pre-Phase-9 and Phase 8 backup trees. | No available snapshot or change record identifies the exact author, earlier baseline, or reason for its hash. |
| `mlops/status.py` | Current file differs from the fingerprint and has a 2026-11-05 timestamp. It is absent from the checked backup trees. | Same: provenance cannot be established from the available evidence. |

Do not overwrite these files or describe them as Phase 9 changes without an independent source-of-truth copy or review.

**Accounting check:** 3 Phase 9 frontend wiring files + 1 Phase 9 reconstructed document + 3 audit-fix files (including the Phase 9 retention wiring in `app/main.py`) + 10 earlier user-requested fixes + 16 pre-Phase-9 snapshot divergences + 2 unresolved `mlops` divergences = **35**.

## 3. The exact three missing fingerprint paths

The Phase 10 fingerprint records these entries, but the current project, Phase 10 staging tree, `TriChurn_Pre_Phase9_Backup_20261110_231500`, `Customer Churn Prediction_BACKUP`, and `Customer Churn Prediction_PHASE8_BACKUP` do not contain the corresponding files:

| Missing path | Fingerprint SHA-256 | Finding |
|---|---|---|
| `README_PHASE6.md` | `e209e137f5e20be38b5e070c932b6096f8ba86cb5aa581167ca918ab887eec53` | No verified copy found in the inspected project or backups. |
| `docs/phase7.md` | `26fc68249212dab9a1a2857557da5ea8a8667fc8e7d080444a96ae9031ddf932` | No verified copy found in the inspected project or backups. |
| `requirements-phase6.txt` | `92615826f67a1b7e18eb3ba4f78e73b0d50715197ae2e2cfb0bf2e85f1441c17` | No verified copy found in the inspected project or backups. |

`PHASE9_CHANGELOG.md` reports no Phase 1–8 baseline files deleted by Phase 9. That is evidence against attributing these absences to the documented Phase 9 overlay, but does not prove when or how they became absent: no complete pre-Phase-9 snapshot contains them, and no Git history exists. Their loss is therefore **unresolved**, not a verified Phase 9 deletion and not proven harmless. Before integration, decide whether they are required project documentation/dependencies; if recovery is needed, obtain them from a trusted source and compare to the fingerprints before restoring.

## 4. Authoritative baseline for the Phase 9-integrated project

### What exists now

- `PHASE9_MANIFEST.txt` verifies files from the Phase 9 package; it is not a checksum inventory of the entire project.
- `PHASE9_BASELINE_DIFF.txt` records the intended before/after hashes for four Phase 9 wiring files; it does not include subsequent audit fixes or every Phase 1–9 file.
- `PHASE9_TEST_REPORT.md` documents test/audit results and two fixes; it is not a whole-tree content baseline.
- `TriChurn_Pre_Phase9_Backup_20261110_231500` is explicitly pre-Phase 9, so it cannot serve as the post-integration authoritative snapshot.
- The Phase 10 `BASELINE_P1_8` is a pre-Phase-10 Phase 1–8 fingerprint, not a Phase 9-integrated baseline. It should not be used to overwrite or “repair” the current Phase 9 tree.
- There is no `.git` repository in the project or its ancestor directories, and no verified full-tree Phase 9 post-audit SHA-256 manifest was found.

### Conclusion

**No single authoritative, immutable, whole-project Phase 9 baseline currently exists in the inspected workspace.** For content, the best operational reference is the current Phase 9-integrated tree together with the Phase 9 audit report, Phase 9 package manifest, and the clarified mismatch accounting in this plan. That is still not an independently reproducible full-tree baseline.

After the user approves the Git/backup steps below, establish the authoritative baseline by:

1. Resolving the two `mlops` provenance questions and deciding how to handle the three absent files.
2. Creating and verifying a complete, fresh backup outside the project.
3. Generating a SHA-256 inventory of the full current project tree, with explicit exclusions documented (virtual environments, caches, generated build outputs, local secrets, and data if intentionally excluded).
4. Creating a reviewed initial Git commit for approved source/config/docs only, or an equivalently immutable archival snapshot. Do not stage model binaries, the raw dataset, local databases, secrets, or caches.
5. Saving the manifest and commit ID together as the Phase 9 baseline record. Do not call the old Phase 1–8 fingerprint a Phase 9 baseline.

The Phase 9 model artifacts remain separate integrity anchors: the Phase 2 and Phase 5 model SHA-256 values recorded in Phase 9 documentation are `db399a55f650c6681e1caaf52257f909777e2c5fada3af5911370ddf5b8ff1ad` and `38423c9cf19b05aa35b72acd44ea3a8af4c3775a1e6cf2bb739ee1972dc05927`. They were not changed during this read-only investigation.

## 5. Safe Git initialization plan for Windows

### Verified current state

- `git` is installed (`git version 2.53.0.windows.1`).
- No `.git` directory exists at the project root or in its parent directories.
- The root `.gitignore` already excludes `.env`, `.venv/`, raw CSV, processed data, model `.joblib` files, and some generated experiment reports. Review additional local databases, Airflow state, and future DVC runtime files before staging.
- No Git command that initializes or stages the project was run.

The official [`git init` documentation](https://git-scm.com/docs/git-init) describes creation of repository metadata (`.git`) and states that initialization does not overwrite existing files. That does not make an unreviewed initial commit safe: it can still accidentally add sensitive or generated files.

### Proposed commands — do not run until separately approved

Use the existing project root and a reviewed file allow-list. Keep a verified backup first.

```powershell
$root = 'C:\Users\ASUS\Downloads\Customer Churn Prediction'
git -C $root status --short --ignored
git -C $root init --initial-branch=main
git -C $root status --short --ignored
```

`git init` should add metadata only. Do not use `git add .`, `git add -A`, `git clean`, `git reset --hard`, or checkout/restore commands as setup or rollback shortcuts.

Before any real stage operation:

1. Review `.gitignore` and confirm `.env*` secrets (while deliberately preserving safe example files), `.venv`, SQLite campaign databases, DVC cache/config-local, raw customer CSV, model binaries, generated data, and build outputs cannot be staged.
2. Preview an explicit source/document allow-list with `git add --dry-run -- <paths>` (`-n` is documented as not adding files); inspect `git status --short`, `git diff --cached --name-status`, and `git diff --cached --stat` after any approved actual staging.
3. Review the staged diff and all ignored/untracked paths. Only then make an initial commit if separately approved. Do not add a remote, push, or commit without the user's approval.

To keep DVC commands using the project dependencies, run `dvc` from a shell whose active `python` is the project DVC/application environment. DVC stages in the supplied YAML use commands such as `python scripts/...`; a separate DVC-only environment will otherwise run those scripts under the wrong Python unless its `PATH` is deliberately configured.

## 6. Exact DVC and remote requirements for this Windows environment

### Verified environment and package metadata

- The selected project interpreter reports **Python 3.13.14**.
- DVC is not installed in that environment.
- The Phase 10 requirement currently says only `dvc>=3.50`; that is an open-ended lower bound, not a reproducible pin.
- The overlay documentation reports DVC 3.67.1 tested on Linux/Python 3.12.3; it does not establish that DVC or the full Phase 10 stages were run on this Windows/Python 3.13 environment.
- PyPI metadata for [DVC 3.67.1](https://pypi.org/project/dvc/3.67.1/) reports `Requires-Python >=3.9`, includes a Python 3.13 classifier, and publishes a `py3-none-any` wheel. Therefore the selected Python version satisfies declared package metadata. This does **not** prove that the project's full dependency set resolves cleanly or that DVC stages work on this Windows host.

### Recommended installation choice after approval

Use the package version already recorded as tested by the overlay, but first run a resolver dry-run in a disposable environment. Do not install into the current `.venv` until the dry-run proves it will not unexpectedly replace or downgrade the existing ML/API dependencies.

Recommended pinned base package:

```powershell
python -m pip install "dvc==3.67.1"
```

For an actual project pipeline, the active environment must also have the project's ML dependencies (`requirements.txt` and, where needed, the API/Phase 8 manifests). Prefer a separate environment outside the project working tree if isolation is needed; install the complete required project dependency set plus pinned DVC into it, then activate it before running DVC so stage commands resolve `python` to that same environment. If the combined resolver proposes unrelated dependency upgrades/downgrades, stop and request a decision; do not silently change existing package manifests.

Do not install Apache Airflow on native Windows. The official [Airflow prerequisites](https://airflow.apache.org/docs/apache-airflow/stable/installation/prerequisites.html) state that Airflow is supported on POSIX/Linux, with Windows use through WSL2 or Linux containers; production is supported only on Linux-based distributions. Keep Airflow in its own Linux/WSL2/Docker environment and install it with that Airflow release's official constraints file. It is intentionally not part of `requirements-phase10.txt`.

### DVC remote configuration

- **No remote is currently configured.** The staged `.dvc/config` only disables analytics and update checks. No DVC cache object was found in the inspected locations.
- A local filesystem remote requires the base `dvc` package; it does not require a cloud extra. Use a storage directory outside the project and preferably outside the same drive/failure domain. Example only:

  ```powershell
  dvc remote add --local --default trichurn_local "D:\DVCStore\TriChurn"
  ```

  This should store the machine-specific remote in ignored `.dvc/config.local`, not in committed `.dvc/config`. The actual directory, permissions, backup policy, and whether a shared remote is desired are user decisions.

- For cloud remotes, install the matching optional DVC extra at the same pinned version (examples: `dvc[s3]==3.67.1`, `dvc[azure]==3.67.1`, `dvc[gs]==3.67.1`, `dvc[ssh]==3.67.1`). Credentials must come from the provider's normal credential chain/environment or ignored local configuration. Never put secrets in `.dvc/config`, committed YAML, a repository URL, or source code.
- A shared, non-secret remote name/URL can be committed only after approval. Credentials or machine-specific URLs belong in ignored local configuration. A remote also needs appropriate read/write permissions and approval for storing this customer dataset.
- The CSV currently matches the staging DVC pointer, but the missing cache/remote means the pointer alone cannot restore the CSV. In a disposable copy, verify a controlled `dvc add`/cache-population strategy for the already-present CSV and compare the resulting pointer hash/size; do not run it in the canonical project as part of this audit.
- The overlay's root pipeline declares locked model binaries as `persist: true` DVC outputs. This behavior is **not locally validated**. Exercise the exact pipeline only in a disposable copy and verify all four model/sidecar hashes and the `models/` listing before and after any checkout/repro/cache operation. DVC may affect file timestamps or relink outputs even when bytes remain identical.

The official DVC documentation links in the staging package point to [installation](https://dvc.org/doc/get-started/install), [remote storage](https://dvc.org/doc/user-guide/data-management/remote-storage), and [remote add](https://dvc.org/doc/command-reference/remote/add). Those pages could not be fetched in this network session; package compatibility facts above were independently checked against PyPI metadata. Treat precise DVC CLI behavior and Windows remote-path behavior as items to confirm in the disposable integration test before using the canonical project.

## 7. Airflow DAG shell-command risk and safe approach

### Verified risk

The staged DAG interpolates `dag_run.conf['candidate_version']` directly into quoted `BashOperator` command strings for:

- `model_training`
- `candidate_artifact_validation`
- `candidate_evaluation`
- the separate `promote_approved_candidate` task

The shell quotes do not make a Jinja-substituted value safe: a malicious value can include a quote and shell syntax. Candidate validation in the invoked script is too late because the shell parses the command first. The separate promotion DAG has no training-gate task, so a principal permitted to trigger it with arbitrary DAG-run configuration can reach the shell interpolation directly. In the main DAG, the ordinary path first passes through `_training_allowed`, which rejects invalid candidate versions when training is enabled and requested; that gate is a useful defense, but it does not make shell interpolation a sound boundary for downstream tasks or the separate promotion DAG. Airflow trigger permissions were not audited.

The official [Airflow BashOperator documentation](https://airflow.apache.org/docs/apache-airflow-providers-standard/stable/operators/bash.html) warns against interpolating untrusted values into `bash_command` and recommends passing values via `env` when using Bash. For this DAG, the stronger recommended design is to avoid a shell for all candidate-dependent commands:

1. Replace the candidate-dependent BashOperators with PythonOperator task callables. Read `dag_run.conf` from Airflow context (no Jinja inside command text).
2. Require `type(candidate_version) is str` and validate the full version against the same strict candidate-version rule used by `pipeline.gate` **inside each callable** before spawning a process.
3. Invoke the project interpreter and script using an argument list, e.g. `subprocess.run([PYTHON, str(ROOT / "scripts" / "train.py"), "--candidate-version", candidate_version, "--confirm-training"], cwd=ROOT, check=True, shell=False, timeout=...)`. Keep `PYTHON` as one executable path, not a shell command string.
4. For promotion, accept confirmation only if the configuration value is the boolean `True`, construct `--confirm` as a separate argv item only then, and still let the promotion script enforce its own approval record. Restrict permission to trigger the promotion DAG to authorized operators; a paused-on-creation DAG is not an authorization control.
5. Catch no validation/process failures into success-shaped results; propagate a failed exit code so Airflow reports task failure. Preserve explicit task timeouts and the manual training gate.
6. Add tests that submit shell metacharacters/newlines as candidate values and assert rejection occurs before `subprocess.run`; mock the process runner so the tests do not train, approve, or promote. Add an Airflow DAG parse test in the supported Linux environment.

Passing a candidate through a quoted shell environment variable is safer than command-string interpolation but still leaves a shell in the execution path. Prefer argv with `shell=False` here. Keep fixed, non-user-controlled data-stage Bash commands only if they remain constant strings; do not template customer-provided or DAG-run text into them.

## 8. Revised integration checklist, preconditions, rollback, and verification

This is a future sequence only. No command below was executed except read-only checks explicitly described earlier.

### Phase A — Preconditions

- [ ] Obtain explicit approval to begin integration; this document is not that approval.
- [ ] Reconcile the 35 paths using the accounting above. For the 16 pre-snapshot unexplained files and two `mlops` files, confirm intended content against a trusted source or accept them explicitly as the Phase 9 baseline. Do not restore files from the old fingerprint automatically.
- [ ] Decide whether the three missing paths are required and recover only from a trusted source, with SHA verification. Record the decision if intentionally absent.
- [ ] Make a fresh, complete Phase 9 pre-integration backup at a new, unique sibling path; verify nonexistence before creating. Do not overwrite any existing backup, especially `TriChurn_Pre_Phase9_Backup_20261110_231500`.
- [ ] Hash and inventory the backup. Confirm both locked model hashes and the exact four-file `models/` listing. Preserve the dataset and all generated data/artifacts.
- [ ] Establish a post-audit whole-tree baseline (manifest plus reviewed Git commit or immutable archive) before Phase 10 edits.
- [ ] Decide Git branch/repository ownership and approve `git init`; decide whether to create an initial commit. Do not add a remote or push without separate approval.
- [ ] Select the DVC version and storage target. Perform a dependency resolver dry-run in a disposable environment; stop if it would disturb the existing dependency set.
- [ ] Fix and test the Airflow candidate-command handling before adding or enabling the DAG. Keep Airflow Linux/WSL2/container-only.
- [ ] Resolve the DVC pointer/cache question and model `persist: true` output semantics in a disposable copy. No DVC operation against canonical model files until that test is reviewed.

### Phase B — Isolated integration

- [ ] Create a disposable integration worktree/copy from the verified baseline; retain the untouched baseline directory.
- [ ] Add Phase 10 source/config/tests as an explicit file allow-list. Preserve `requirements.txt`, API and Phase 8 manifests, current root `.gitignore`, Phase 1–9 APIs/settings/providers, model files, data, and generated artifacts.
- [ ] Do not seed runtime `ml/experiments/phase10/*.json` with staging reports. Keep verification and training transcript files in staging unless a deliberate documentation decision is made.
- [ ] Initialize DVC only after Git exists in that disposable repo. Merge settings; do not copy `.dvc/` wholesale. Keep remote credentials/local URLs out of committed config.
- [ ] Regenerate `dvc.lock` from the exact final source/config tree only after DVC compatibility tests. Do not trust the staging lock as the lock for the current Phase 9 tree.
- [ ] Keep `training/dvc.yaml` separate from root `dvc.yaml`. Do not run training, approval, or promotion.

### Phase C — Verification gates

Run in the disposable copy and record exact output:

```powershell
# Git and working-tree safety (after approved initialization)
$root = 'C:\Users\ASUS\Downloads\Customer Churn Prediction'
$python = Join-Path $root '.venv\Scripts\python.exe'
git -C $root status --short --ignored
git -C $root diff --check
git -C $root add --dry-run -- <reviewed-source-paths>

# Interpreter / dependency state (no install implied by these checks)
& $python --version
& $python -m pip check

# After approved DVC setup; static inspection only
dvc --version
dvc status
dvc dag dvc.yaml
```

For dependency resolution, use `python -m pip install --dry-run "dvc==3.67.1"` first in a disposable environment; inspect the full resolver plan before any install. If a cloud backend is selected, include only that backend's DVC extra. Do not use a credential-bearing URL in command history.

The following are **later, separate approval gates**, not part of this read-only investigation: run the isolated Phase 10 tests; exercise data-only DVC stages in the disposable copy; validate the Airflow DAG in Linux; compare model/data hashes and run Phase 1–9 regressions. Do not use a root `dvc repro` that includes manual training. For any future DVC reproduction, specify only the approved non-training stage targets and run only in the disposable copy.

Before/after comparison commands:

```powershell
$root = 'C:\Users\ASUS\Downloads\Customer Churn Prediction'
$modelPaths = @(
  (Join-Path $root 'models\trichurn_churn_model_v2.0.0.joblib'),
  (Join-Path $root 'models\trichurn_churn_model_v2.0.0.metadata.json'),
  (Join-Path $root 'models\trichurn_segmentation_v5.0.0.joblib'),
  (Join-Path $root 'models\trichurn_segmentation_v5.0.0.metadata.json')
)
Get-FileHash -Algorithm SHA256 $modelPaths
Get-ChildItem -LiteralPath (Join-Path $root 'models') -File | Select-Object -ExpandProperty Name | Sort-Object
```

Also compare the full approved SHA-256 inventory, `git status --short`, DVC lock, and exact file additions against the recorded baseline. Fail closed on any model, sidecar, Phase 1–9 file, or unexpected file-list change.

### Phase D — Rollback

- [ ] Keep the original baseline and verified backup untouched throughout.
- [ ] If a check fails, stop Airflow/DVC processes and preserve logs, command output, and DVC status for diagnosis.
- [ ] Prefer abandoning the disposable integration copy or switching to a separately preserved baseline worktree. Do not use `git reset --hard`, `git clean`, broad recursive deletion, or restore the old fingerprint over the project.
- [ ] If a specific file must be restored, first compare it to the verified backup and restore only that explicitly approved path. For any locked model mismatch, stop all pipeline operations and restore only the named model file from the verified backup under an approved recovery procedure; recheck all model and sidecar hashes afterward.
- [ ] Never roll back by deleting broad data/artifact directories. Preserve generated data and DVC cache until its ownership and reproducibility are confirmed.
- [ ] Keep the failed integration branch/copy and logs for review; do not push or overwrite the Phase 9 baseline.

## 9. Final blocker disposition

| Blocker | Current resolution |
|---|---|
| Explain the 35 mismatches | Accounted for file-by-file in six evidence groups. Most are documented Phase 9/audit edits or already present in the pre-Phase-9 snapshot. The 16 snapshot divergences lack individual provenance; two `mlops` paths lack a comparator. |
| Identify the 3 missing paths | Exact paths and recorded hashes are listed. Their disappearance timing/cause remains unverified. |
| Identify authoritative Phase 9 baseline | None exists as a complete immutable full-tree manifest/commit. The project needs a fresh post-audit baseline after review. |
| Safe Git setup | A non-destructive, explicit, allow-listed procedure is documented. Git has not been initialized. |
| Exact Windows DVC requirements | Current Python is 3.13.14; DVC 3.67.1 metadata supports Python >=3.9 and includes Python 3.13. It is not installed; Windows pipeline compatibility and dependency resolution remain to be tested. |
| Remote requirements | No remote/cache is currently configured/found. Local remote needs base DVC and a separate writable storage path; cloud remotes need the corresponding DVC extra and external credential handling. |
| Airflow command risk | Confirmed in four tasks. Replace candidate-dependent shell commands with validated PythonOperator callables invoking argv with `shell=False`; test injection strings before deployment. |
| Rollback and verification | Checklist and non-destructive rollback gates are documented above. |

**Stop point:** Await user approval. No integration, Git initialization, dependency installation, DVC command, model training, approval, or promotion has been performed.

## Sources

- [DVC 3.67.1 on PyPI](https://pypi.org/project/dvc/3.67.1/) — release metadata for `Requires-Python`, Python classifiers, and wheel.
- [Git `init` documentation](https://git-scm.com/docs/git-init) and [Git `add` documentation](https://git-scm.com/docs/git-add) — repository creation and `--dry-run`.
- [Airflow installation prerequisites](https://airflow.apache.org/docs/apache-airflow/stable/installation/prerequisites.html) — supported operating systems and WSL2/container guidance.
- [Airflow BashOperator documentation](https://airflow.apache.org/docs/apache-airflow-providers-standard/stable/operators/bash.html) — warns against interpolating untrusted values into `bash_command` and describes environment passing.
- [DVC installation](https://dvc.org/doc/get-started/install), [remote storage](https://dvc.org/doc/user-guide/data-management/remote-storage), and [remote add](https://dvc.org/doc/command-reference/remote/add) — official references; these DVC documentation pages were unavailable through the web retriever during this audit, so Windows CLI/path behavior remains a verification item.
