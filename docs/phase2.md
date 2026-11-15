# Phase 2: Model optimization, calibration, thresholding and final evaluation

Built on top of Phase 1.1 without changing it. Reuses `split_raw`, `plan_features`,
`validate_training_data`, `prepare_xy`, `build_pipeline`, `make_estimator`, `cross_validate_pipeline`,
`cv_splitter` and `compute_metrics`. Command: `make optimize` (= `python scripts/run_phase2.py`).

## Flow

```
RAW -> split_raw (Phase 1.1, stratified, seed 42)  ->  TRAIN | VALIDATION | TEST

run_optimization_decisions(train_df, val_df, ...)          <- has NO test parameter
  TRAIN only : plan_features -> leakage screen -> tuning (stratified CV)            [tuning.py]
  TRAIN + VAL: fit best config of each model on TRAIN, compare on CV + VALIDATION   [model_selection.py]
  TRAIN->VAL : calibrator fitted on TRAIN out-of-fold predictions, compared on VAL  [calibration.py]
  VALIDATION : decision threshold optimised on calibrated validation probabilities  [thresholding.py]
  lock_model(...) -> LockedModel + SHA-256 fingerprint of every decision            [final_evaluation.py]
evaluate_on_test(locked, test_df, spec)                    <- first and ONLY read of TEST, once
save_artifact(...)                                         <- joblib + metadata JSON [serialization.py]
```
`optimization.py` orchestrates (`run_optimization`, `run_optimization_on_splits`,
`run_optimization_decisions`). All policy lives in `configs/optimization.yaml`; the split ratios and the base
seed stay in `configs/training.yaml`.

## Reproducibility settings
| Item | Value (configurable) |
|---|---|
| random_state | `optimization.seed`; `null` inherits `training.seed` = 42. Used for CV folds, parameter sampling, estimators and calibration folds |
| CV strategy | `StratifiedKFold(n_splits=5, shuffle=True, random_state=seed)` on TRAIN; **identical folds** for every candidate |
| Scoring metrics | accuracy, precision, recall, F1, ROC-AUC, PR-AUC (mean and std over folds) |
| Search | seeded random search (`sklearn.model_selection.ParameterSampler`), capped at the grid size |
| Budget | LR 14, RF 18, XGB 24 sampled candidates + the 2 Phase 1.1 baseline configs per model, x 5 folds |
| Ranking | mean CV `pr_auc`, tie-break `roc_auc` (config: `tuning.primary_metric`, `tiebreak_metric`) |

Search spaces (all in `configs/optimization.yaml`; `imbalance` is the `class_weight` switch - `none` ->
`class_weight=None` / `scale_pos_weight=1`, `balanced` -> `class_weight="balanced"` (RF: `balanced_subsample`)
/ `scale_pos_weight=neg/pos`; no resampling, as in Phase 1):

| Model | Searched parameters |
|---|---|
| Logistic Regression | `C` {0.01..10}, `solver` {lbfgs, liblinear, saga}, `imbalance`, `max_iter` 3000 |
| Random Forest | `n_estimators` {200,300,500}, `max_depth` {4,6,8,12,None}, `min_samples_split` {2,5,10,20}, `min_samples_leaf` {1,3,5,10}, `max_features` {sqrt,log2,0.5}, `imbalance` |
| XGBoost | `n_estimators` {100..500}, `max_depth` {2..6}, `learning_rate` {0.01..0.1}, `subsample`, `colsample_bytree` {0.6,0.8,1.0}, `min_child_weight` {1,3,5,10}, `reg_alpha` {0,0.1,1}, `reg_lambda` {1,3,10}, `imbalance` |

The Phase 1.1 default parameters are always evaluated as candidates, so the tuned CV score can never be
below the baseline, and the report shows tuned vs baseline.

## Methodology
**Tuning.** Every candidate is cross-validated as the *full* Phase 1.1 pipeline (coerce -> engineer ->
impute/scale/encode -> estimator), so every learned transformer is re-fitted inside each fold. Only
`X_train, y_train` are accepted.

**Model comparison.** The best tuned configuration of each model is fitted on TRAIN and scored on VALIDATION.
The winner has the highest composite `0.5 * CV + 0.5 * VALIDATION` over weighted metrics
`{pr_auc: 0.4, roc_auc: 0.3, f1: 0.2, recall: 0.1}` (all configurable). PR-AUC and ROC-AUC are threshold-free;
F1 and recall are evaluated at each model's own decision threshold, optimised on that model's TRAIN out-of-fold
probabilities (not a fixed 0.5; on VALIDATION that TRAIN-derived threshold is applied unchanged). They still
depend on the model and class-weighting strategy, so their combined weight is deliberately smaller. The final
production threshold is a separate step, optimised on VALIDATION after calibration. All metrics of all models are reported, not just the composite.
The Phase 1.1 baseline's validation scores are reported for information only and never used to select.

**Calibration.** Class-weighted models over-predict probabilities, so calibration matters. For the selected
model, out-of-fold probabilities are produced on TRAIN (stratified K-fold, full pipeline re-fitted per fold).
Candidates: `none` (uncalibrated), `sigmoid` (Platt scaling on the log-odds), `isotonic`. Calibrators are
fitted on TRAIN out-of-fold predictions and TRAIN labels only; the base pipeline is fitted on all of TRAIN.
All candidates are compared on VALIDATION (Brier, log loss, ROC-AUC, PR-AUC, expected calibration error and
reliability bins). The method with the lowest validation Brier score (config `calibration.select_by`) is
selected, with a parsimony rule (`calibration.min_improvement`, default 0.0005): methods are considered in
`methods` order (none < sigmoid < isotonic) and a more complex one is only preferred if it improves the metric
by more than that margin. A model that is already well calibrated therefore keeps `none` instead of switching to
a step-function isotonic mapping for a noise-level gain.

**Threshold optimisation.** The threshold is chosen on VALIDATION from the *calibrated* probabilities by a
grid search (0.05-0.95 step 0.005). Objective: F1 (config `threshold.metric`: `f1`, `f_beta`, or
`recall_at_precision`). Plateaus of equal value resolve to their median. `threshold.override` can force a
policy threshold; it is still reported with its validation precision/recall/F1. `optimize_threshold` takes
only `(y_val, p_val, config)`.

**Final evaluation.** `lock_model` freezes model, hyperparameters, calibrator and threshold and computes a
SHA-256 fingerprint over the decisions and the model's behaviour on a few validation rows.
`evaluate_on_test` (the only reader of TEST) verifies the fingerprint before and after scoring, refuses to run
twice (`TestSetAlreadyEvaluatedError`), and fits/calibrates/tunes nothing. It reports **probability metrics**
(ROC-AUC, PR-AUC, Brier, log loss - threshold-free) separately from **threshold-dependent metrics** (accuracy,
precision, recall, F1, confusion matrix at the validation-selected threshold).

## Test isolation
**TEST data is reserved for the single final evaluation.** It never influences tuning, model selection,
calibration, the threshold or the lock. Enforced by construction (no decision function has a test parameter;
`run_optimization_decisions` takes only train and validation) and proven by `tests/unit/test_phase2_test_isolation.py`:
changing test labels/features/population leaves every tuning, selection, calibration and threshold output and
the lock fingerprint bit-identical (while the final test metrics do change); controls prove the same outputs
*do* react to train/validation changes; marker-column spies prove no test row reaches any fit, CV, calibrator
or threshold call; an event-order spy proves the test is read last, exactly once; a static AST scan proves the
decision modules never reference a test identifier.

Honest limitation: validation is reused for model comparison, the calibration-method choice and the threshold.
That makes the *validation* numbers mildly optimistic; it is why the unseen TEST split is the number to quote.

## Serialization
`models/trichurn_churn_model_v<version>.joblib` (git-ignored) holds `{schema_version, model, threshold,
metadata}`; the model is the calibrated pipeline and accepts **raw customer records**. The sidecar
`.metadata.json` repeats the metadata plus the artifact SHA-256. Metadata: model name/version, UTC training
time, raw input feature names and count, post-encoding feature names and count, calibration method and fitted
parameters, threshold (value, metric, source), hyperparameters, imbalance strategy, random state, full
training/feature/optimization configuration, tuning summary, CV / validation / test metrics, dataset path
(repo-relative), version hash and split sizes, decision fingerprint and library versions. Paths are anchored at
the project root; no machine-specific path is stored. Load with `ml.pipelines.serialization.load_artifact`.

Run output: `ml/experiments/phase2_report.json`.

## Results on the IBM Telco dataset (`make optimize`, seed 42)
Split 4,929 / 1,057 / 1,057 (train / validation / test). Dataset `sha256:16320c9c1ec7`.

| Model (tuned) | CV PR-AUC | CV ROC-AUC | Val PR-AUC | Val ROC-AUC | Composite |
|---|---|---|---|---|---|
| Logistic Regression | 0.6647 | 0.8466 | 0.6417 | 0.8332 | **0.7184** |
| Random Forest | 0.6669 | 0.8475 | 0.6279 | 0.8325 | 0.7144 |
| XGBoost | 0.6729 | 0.8491 | 0.6348 | 0.8351 | 0.7142 |

Selected: Logistic Regression (`C=3.0`, lbfgs, no class weighting). The margin is 0.004: the three models are
practically indistinguishable here, so the choice is a tie-break, not strong evidence. Tuning improved CV
PR-AUC over the Phase 1.1 defaults only slightly (+0.001 to +0.011).

Calibration (validation): `none` Brier 0.1393 / log loss 0.4313 / ECE 0.019; sigmoid 0.1392 / 0.4306 / 0.021;
isotonic 0.1392 / 0.4311 / 0.029. `none` is selected: LR is already well calibrated and no method clears the
0.0005 parsimony margin.

Threshold (validation, F1): 0.34 -> precision 0.567, recall 0.712, F1 0.631.

Final TEST (evaluated once, after the lock). Probability metrics: ROC-AUC 0.8492, PR-AUC 0.6412, Brier 0.1355,
log loss 0.4107. At threshold 0.34: accuracy 0.7711, precision 0.5503, recall 0.7429, F1 0.6322.

Design notes. (1) Model comparison uses F1/recall at each model's own TRAIN out-of-fold-optimal threshold,
because at a fixed 0.5 the class-weighting strategy, not model quality, drives those numbers. (2) Calibration
uses a parsimony margin so noise-level Brier gains do not select a more complex calibrator. Both were decided
from validation evidence and methodology.
