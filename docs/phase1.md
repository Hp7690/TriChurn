# Phase 1: Dataset + ML foundation

## Data flow and test isolation (Phase 1.1)

```
RAW DATA
  -> DATASET VALIDATION   structural / schema checks on the full raw data (descriptive only)
  -> PROFILE + QUALITY    descriptive statistics of the raw data (feed no decision)
  -> STRATIFIED SPLIT     train / validation / test (seed + ratios from configs/training.yaml)
        TRAIN only:  feature planning -> TRAINING VALIDATION (leakage screen) -> CV -> fit
        VALIDATION:  scoring / model comparison of the fitted pipelines
        TEST:        created by the split, then never read in Phase 1
```

Principle: **the TEST set is untouched until the final evaluation**, and nothing that is target-informed or
that learns from data may see validation or test rows.

### Dataset validation (`validate_dataset`) - raw/full data
Structural only: empty dataset, target exists, declared columns exist, row count, target class counts (needed
to know a stratified split is feasible), duplicate IDs, unsupported types, unparsable/extreme numerics, basic
missingness, duplicate rows. It never runs a target-informed screen and selects no features or models.

### Training validation (`validate_training_data`) - TRAIN only
Anything that can influence an ML decision: the target-informed **leakage screen** (name match, categorical
columns that reproduce the target, single-feature AUC) and the report of features dropped by the plan. It
accepts only the train frame, a train-fitted `FeaturePlan` and config; there is no parameter through which
validation/test rows could enter. Leakage suspects are hard errors (the run is rejected).

### Feature planning (`plan_features(train_df, ...)`) - TRAIN only
Constant, all-null, ID-like and high-missing decisions, and numeric-vs-categorical inference, are made from
the train rows. A column that is constant in TRAIN but variable in TEST is dropped (TRAIN decides); a column
that only looks leaky in TEST is not flagged. Validation rows are projected onto the train-decided column
list (`prepare_xy`) and nothing more.

### Data split
The stratified split happens on the raw frame **before** any target-informed ML decision
(`split_raw`). Stratification reads the labels to assign rows to partitions - that is the only use of
validation/test labels before evaluation, and it makes no feature or model decision. Rows with no target are
removed first. Seed, ratios and stratification are unchanged, so the partition is identical to Phase 1.

### Test isolation
`run_training_on_splits` takes the test frame but reads only `len(test_df)` (for the report). No fitting,
planning, screening, CV or model comparison touches it. The test split is reserved for the final evaluation.
`profile` / `quality` in the report are descriptive statistics of the raw dataset and are not used by any
decision.

## Data Quality Score (0-100)
Start at 100 and subtract five capped penalties (all thresholds in `configs/quality.yaml`).
Datasets that fail hard validation are **Rejected** and are not scored.

| Component | Cap | Full penalty when |
|---|---|---|
| missing | 30 | 20% of feature cells are missing (blank strings count as missing) |
| duplicates | 20 | duplicate rows + duplicate IDs reach 10% of rows |
| structure | 10 | 20% of feature columns are constant / all-null / ID-like |
| imbalance | 15 | minority share <= 1% (penalty starts below 10%) |
| sample_size | 15 | proportional below 1,000 rows |

Bands: Excellent >= 90, Good 75-89, Needs Attention 50-74, Poor < 50. Because penalties are capped, the lowest
possible score is 10. The per-component breakdown is returned with every score.

## Hard validation errors (dataset rejected)
empty dataset, missing target, all-null target, one-class target, minority class < 20 rows, < 100 rows,
duplicate customer IDs, unsupported types (datetime/nested), non-numeric values in > 5% of a numeric column,
|values| > 1e12, > 50% of feature values missing (all *dataset validation*, raw data), and - from *training
validation*, TRAIN split only - **possible target leakage**.
Warnings (handled, not fatal): partial null target (rows dropped), duplicate rows, empty columns and per-column
missing counts (dataset validation); a few non-numeric or infinite values (-> missing); and `FEATURE_DROPPED`
for constant / all-null / ID-like / > 60% missing columns, decided on TRAIN only (training validation).

## Leakage controls
1. Stratified train / validation / test split happens **before** feature planning, leakage screening or anything
   is fitted. Test is unused in Phase 1.
2. Coercion, feature engineering, imputation, scaling and encoding are all inside one `sklearn.Pipeline`,
   so `cross_validate` re-fits them per fold. `StratifiedKFold` is used.
3. Feature engineering never sees the target; learned values (charge-band quantiles) are learned in `fit()`.
4. Leakage screen before training, **on the TRAIN split only**: column names containing the target name,
   categorical columns that reproduce the target (balanced accuracy >= 0.99), numeric columns with
   single-feature ROC-AUC >= 0.99.
5. Tests: per-fold fit-set spy, train-only imputer/scaler/encoder statistics, disjoint stratified splits,
   a negative control proving the spy check can fail, and rejection of leaky columns.
6. Isolation tests (`tests/unit/test_test_isolation.py`): changing only validation/test labels or features
   cannot change the leakage screen, feature plan, engineered features or CV results; a feature constant in
   TRAIN but variable in TEST is dropped; a leak-like feature present only in TEST is not flagged; spies prove
   planning, screening, CV and every `fit` receive TRAIN rows only and TEST rows are never transformed; the TEST
   argument can be replaced by an object supporting only `len()`. Each isolation test carries a control showing
   the old pooled-data behaviour would have changed the outcome.

These are heuristics: they catch obvious leaks, not subtle temporal ones. Whether a column is known *before*
the churn event is a domain question the user must confirm.

## Engineered features
See `FEATURE_DOCS` in `ml/pipelines/feature_engineering.py`. Role-to-column mapping is `configs/features.yaml`;
a feature whose inputs are absent is skipped and reported. `contract_risk` / `payment_risk` are ordinal domain priors
from config, not learned from the target.

## Imbalance
Options compared per model: no handling vs class weights (`class_weight` / `scale_pos_weight`). SMOTE is not used:
resampling distorts predicted probabilities, which the business layer relies on (Phase 4). On Telco the two options
produce nearly identical ranking metrics; weights mainly shift recall at a fixed 0.5 cutoff, which is the job of
threshold optimisation (Phase 2).
