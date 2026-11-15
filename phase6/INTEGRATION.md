# Merging Phase 6 into your existing TriChurn project

Overlay = only new files. Nothing in Phase 1-5 is replaced. Commands are PowerShell; replace the placeholder paths.
`<PROJECT>` is your project root (the folder that contains `ml\`, `models\`, `configs\`, `tests\`).

> Legend. **[CONNECT]** marks a place where your existing Phase 1-5 implementation is attached. With the Phase 1-5
> layout this overlay was built against, every **[CONNECT]** is already wired and you only have to VERIFY it.

## 1. Extract and merge (check for collisions first)
```powershell
cd "<PROJECT>"
$src = "C:\path\to\TriChurn_Phase6_FastAPI"          # the extracted ZIP folder
Get-ChildItem -Recurse -File $src | ForEach-Object {
    $rel = $_.FullName.Substring($src.Length + 1)
    if (Test-Path $rel) { "COLLISION: $rel" }
}                                                     # expected: prints NOTHING
Copy-Item -Recurse "$src\*" .
```
If anything prints `COLLISION`, stop: the overlay must not overwrite an existing file. The overlay adds only:
`app\`, `tests\api\`, `tests\support\`, `tests\unit\test_phase6_*.py`, `docs\phase6.md`, `phase6\`,
`requirements-phase6.txt`, `README_PHASE6.md`. It does NOT touch `tests\conftest.py` or `tests\__init__.py`.

## 2. Install the API dependencies
```powershell
pip install -r requirements-phase6.txt
```
Then merge the four lines of `requirements-phase6.txt` (fastapi, uvicorn, pydantic, httpx) into your `requirements.txt`
(append them; keep every existing line and pin). Do not upgrade scikit-learn, numpy, pandas, shap, xgboost.

## 3. Verify the Phase 2 model exists and is the locked one
```powershell
Test-Path .\models\trichurn_churn_model_v2.0.0.joblib                                   # True
(Get-FileHash .\models\trichurn_churn_model_v2.0.0.joblib -Algorithm SHA256).Hash.ToLower()
# must equal: db399a55f650c6681e1caaf52257f909777e2c5fada3af5911370ddf5b8ff1ad
Test-Path .\models\trichurn_churn_model_v2.0.0.metadata.json                            # True
```
**[CONNECT]** The API pins this digest (`LOCKED_PHASE2_SHA256` in `app\core\config.py`). A different file => 503.

## 4. Verify the Phase 5 artifact and the dataset
```powershell
Test-Path .\models\trichurn_segmentation_v5.0.0.joblib                                  # True
Test-Path .\models\trichurn_segmentation_v5.0.0.metadata.json                           # True
Test-Path .\ml\data\raw\telco_churn.csv                                                 # True (see below)
```
* The Phase 5 file is verified against its own sidecar SHA-256 and must be K=3, seed 42, the 5 locked features.
  To also pin its digest set `$env:TRICHURN_PHASE5_SHA256 = "<64 hex>"` (not pinned by default: no digest was supplied).
* **The explainability endpoint needs the raw TRAIN CSV at runtime**: Phase 3 rebuilds its 100-row SHAP background
  from it. Without the CSV, `/explain` and `/customer-intelligence` answer 503 and `/readiness` is false. Get it with
  `python scripts\download_telco.py` (or `make data`).

## 5. Connect the Phase 1-5 adapter  **[CONNECT]**
The ONLY file that imports your `ml` package is `app\services\adapters\phase15_adapter.py`, and only inside
`default_bindings()`. It binds exactly these existing Phase 1-5 symbols:

| Capability | Existing symbol used |
|---|---|
| model + threshold + metadata | `ml.explainability.load_verified_artifact` (`.artifact.predict_proba`, `.threshold`, `.metadata`) |
| risk band | `ml.business.assign_risk_band`, `ml.business.load_business_config` (`risk_bands`) |
| explanation | `ml.explainability.ChurnShapExplainer`, `load_train_background`, `ml.pipelines.ingestion.DatasetSpec` |
| business | `ml.business.BusinessEngine` (`.profile`, `.explain`) |
| segment | `ml.segmentation.load_verified_segmentation_artifact`, `assign_customers` (nearest centroid only) |
| error mapping | `ml.errors.{BusinessInputError, ExplainabilityInputError, SegmentationInputError, ArtifactIntegrityError}` |

* Same names in your project: **nothing to change.**
* Different names/layout: edit ONLY `default_bindings()`, or copy `phase6\integration_config.example.py`, edit it, and
  set `$env:TRICHURN_ADAPTER_FACTORY = "my_integration:build_adapter"`. Routes, services and schemas never change.
* Different artifact/dataset locations: use the environment variables in `docs\phase6.md` (paths are relative to the
  project root; nothing is hard-coded to a machine).
* **[CONNECT]** `app\schemas\common.py::CustomerFeatures` must list exactly the model's 19 raw features. `/readiness`
  checks this against the model metadata (`feature_schema`) and reports `request_schema_differs_from_model_features`.

## 6. Run the Phase 6 tests
```powershell
python -m pytest tests\api tests\unit\test_phase6_architecture.py tests\unit\test_phase6_config.py `
    tests\unit\test_phase6_locked_artifacts.py tests\unit\test_phase6_integration_example.py -rs
```
Expected: all pass and **zero skips**. A skip whose reason says "existing Phase 1-5 project ... not present" or
"artifact not present" means a prerequisite from steps 3-4 is missing: fix that, do not ignore it.
`tests\api\test_real_integration.py` is the real-integration check (the production adapter against Phase 2-5).

## 7. Run the complete regression suite
```powershell
python -m pytest -q -rs
```
Expected: every existing Phase 1-5 test still passes, plus the Phase 6 tests.

## 8. Ruff
```powershell
ruff check .
```

## 9. Start FastAPI
```powershell
python -m uvicorn app.main:app --host 127.0.0.1 --port 8000
```
Startup loads Phase 2-5 once (a few seconds, mostly the SHAP background). Do not use `--reload` in production.

## 10. Open /docs and check readiness
* Browser: <http://127.0.0.1:8000/docs> (and `/openapi.json`).
* ```powershell
  Invoke-RestMethod http://127.0.0.1:8000/api/v1/readiness     # ready : True
  Invoke-RestMethod -Method Post http://127.0.0.1:8000/api/v1/predict -ContentType "application/json" `
      -Body (Get-Content .\phase6\example_request.json -Raw)
  ```

## Troubleshooting `/readiness` (checks never contain paths)
| check / detail | meaning and fix |
|---|---|
| `phase1_5_modules: modules_not_importable` | the `ml` package is not importable: run from the project root / fix step 5 |
| `phase2_model: artifact_missing` | file not at `models\trichurn_churn_model_v2.0.0.joblib` (step 3) |
| `phase2_model: artifact_sha256_mismatch` | not the locked artifact, or modified after start. Never "fix" by retraining |
| `feature_schema: request_schema_differs_from_model_features` | `CustomerFeatures` != model features (step 5) |
| `explainability: file_missing` | the TRAIN CSV is missing (step 4) |
| `segmentation: segmentation_k_differs_from_locked` (or `_seed_`, `_features_`) | not the locked K=3/seed 42 artifact |
| `*: load_failed` | see the server log (details are logged there, never returned) |
