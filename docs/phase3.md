# Phase 3 - SHAP explainability

Scope: explain the **locked Phase 2 model** (Logistic Regression, calibration `none`, threshold 0.34).
Nothing is retrained, re-tuned, re-calibrated or re-thresholded, and the test split is never read.
Code: `ml/explainability/` (`shap_explainer.py`, `feature_importance.py`, `schemas.py`). Config:
`configs/explainability.yaml`. Tests: `tests/unit/test_shap_explainability.py`.

## What is explained
| Item | Value |
|---|---|
| Explainer | `shap.LinearExplainer`, interventional, `Independent` masker (not Tree/Kernel: the model is a plain logistic regression) |
| Model input | the stored pipeline minus its last step: coerce -> feature engineering -> impute/scale/one-hot (dense; 58 encoded columns on Telco) |
| SHAP output space | **log-odds** (raw margin). `probability = sigmoid(log_odds)` |
| Base value | mean model log-odds over the background rows (Telco: -1.6306) |
| Background | up to `background.max_rows` (100) **raw TRAIN rows**, sampled with `seed` (42); feature columns only |
| Reporting level | **source features**: encoded columns are summed back to the feature they came from |

For a linear model with an independent background, `SHAP_j = coef_j * (x_j - mean_background_j)`, so
`base_value + sum(SHAP) = intercept + coef . x` is exact (up to floating point).

## Artifact integrity
`load_verified_artifact(model_path, metadata_path=None, expected_sha256=None)`:
bytes -> SHA-256 -> compare with the sidecar `artifact_sha256` (or an out-of-band `expected_sha256`) ->
reject on mismatch -> deserialise **those same bytes** (no second read) -> cross-check the embedded metadata against the
sidecar (model name, raw and encoded feature names, calibration method, threshold). Any mismatch raises
`ArtifactIntegrityError` and a tampered file is never unpickled.

The Phase 2 loader `serialization.load_artifact` does **not** verify the hash; it is deliberately unchanged
(Phase 2 is immutable). Phase 3 adds the check around loading instead. Limits: the sidecar sits next to the artifact, so
someone who can rewrite both can also rewrite the digest; pass `expected_sha256` from a release record to close that gap.
joblib files are pickles: only load artifacts whose digest you trust.

## Background (TRAIN only)
`load_train_background(csv, spec, verified)` rebuilds the Phase 2 split from the original CSV using the seed and split
sizes stored in the artifact, **refuses** if the dataset version or the TRAIN row count differs from what Phase 2
recorded, then samples `max_rows` rows from TRAIN (`select_background`). Only the model's feature columns are kept, so the
target and id column cannot enter. Validation and test rows are never touched. The sample is deterministic for a given
TRAIN frame, seed and row order.

## Feature mapping (no hard-coded feature list)
Derived from the fitted `ColumnTransformer` (`transformers_` gives each branch's resolved input columns and fitted
sub-pipeline):
* a branch ending in `OneHotEncoder`: each input column owns `len(categories_[i])` consecutive encoded columns
  (`Contract=Month-to-month`, `Contract=One year`, `Contract=Two year` -> `Contract`);
* any other branch (imputer/scaler): one encoded column -> its input column.

The mapping is cross-checked against `get_feature_names_out()` (width and name prefix) and refused if the encoder uses
`drop` or infrequent-category grouping. Aggregation rule: **source SHAP = sum of its encoded columns' SHAP**
(additive, so totals are unchanged; each encoded column is used exactly once).

Source features are the columns that enter the encoder: the caller's raw columns plus engineered columns
(`tenure_group`, `monthly_charge_band`, `service_count`, `protective_service_count`, `contract_risk`, `payment_risk`,
`monthly_vs_avg_charge_delta`), flagged `is_engineered=true`. Engineered features stay separate, so information in one raw field can be
split between e.g. `Contract` and `contract_risk`; read them together.

## Local explanation
`ChurnShapExplainer.explain(record)` takes **raw** customer fields (dict or one-row DataFrame; no manual encoding) and
returns:

```text
prediction_probability  predicted_class (1 if probability >= threshold)  threshold  base_value  output_space="log_odds"
model_log_odds  reconstruction_error  interpretation
features: [ source_feature, raw_value, shap_value, direction, is_engineered ]   # sorted by |shap_value| desc, then name
```
`direction`: `increases_churn` (shap > epsilon), `decreases_churn` (shap < -epsilon), otherwise `neutral`
(`direction_epsilon`, 1e-9). `raw_value` is the value the model saw after type coercion (`null` = missing, imputed).

**Interpretation.** SHAP values describe how a feature moved the *model's score* relative to the background average;
"increases_churn" means "contributed toward a higher model score", not that the feature caused churn. The
correct wording is "contributed toward a higher/lower model score". `explain_many` returns one explanation per row.

## Global importance and drivers
* `global_importance(X)` -> `(source_feature, mean_abs_shap, rank)`: SHAP is summed to source level **first**, then
  `mean(|.|)` over the rows of `X` (log-odds units). Sorted by importance descending, then feature name; ranks are 1..n.
* `top_positive_drivers(...)`: features with signed log-odds contribution > 0 (toward a higher model score), largest first.
  `top_negative_drivers(...)`: contribution < 0, most negative first. Ties by name; neutral features are excluded.
  Both work on a `LocalExplanation` (module functions) or a raw record (explainer methods).

## Reconstruction (checked on every call)
`base_value + sum(SHAP) == model log-odds` and `sigmoid(log_odds) == model probability` are verified against
`reconstruction.tolerance` (1e-6; observed ~1e-16). A failure raises `ExplainabilityError`; it is never hidden. This
identity holds only for calibration `none`, so a Platt/isotonic model is refused rather than explained inconsistently.

## Input validation
Rejected with `ExplainabilityInputError`: empty input, wrong container type, duplicate columns, missing required
features, non-scalar cells, booleans or non-numeric text in numeric columns, +/-inf. Allowed: blank/null cells (imputed
by the pipeline; `raw_value` is `null`), extra columns (ignored), unseen category values (all-zero one-hot, no contribution).

## Determinism
Same artifact + same background rows + same config -> identical explanations (SHAP values equal to ~1e-12;
tests build two explainers from the same artifact and background and compare them). Background sampling is seeded.

## Known limits
* Interventional SHAP with independent features: correlated inputs (e.g. `tenure` / `TotalCharges`, or a raw field and its
  engineered version) share credit in a way that depends on the background.
* The background is 100 sampled TRAIN rows, so `base_value` carries sampling noise (Telco: -1.63).
* Explanations describe this model only, in log-odds, and say nothing about causes or about what intervention would work.

## Usage
```python
from ml.explainability import ChurnShapExplainer, load_verified_artifact, load_train_background
from ml.pipelines.ingestion import DatasetSpec
spec = DatasetSpec.from_yaml("configs/datasets/telco.yaml")
v = load_verified_artifact("models/trichurn_churn_model_v2.0.0.joblib")
ex = ChurnShapExplainer(v, load_train_background("ml/data/raw/telco_churn.csv", spec, v))
e = ex.explain(customer_dict); ex.top_positive_drivers(customer_dict, 3); ex.global_importance(df_raw)
```
