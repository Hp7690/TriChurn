# Phase 5 - Customer segmentation and segment intelligence

Scope: group customers into deterministic, business-readable segments with **K-Means**, then describe each segment with
the **actual Phase 4 business outputs** (churn risk, CLV, value at risk, ENB, intervention rate, retention strategy).
Phases 1-4 are unchanged; the Phase 2 churn artifact and Phase 3 explanation code are only read.
Code: `ml/segmentation/`. Config: `configs/segmentation.yaml`. Tests: `tests/unit/test_segmentation_*.py`,
`tests/integration/test_segmentation_real_data.py`. Demo: `python scripts/run_phase5.py` (`make segment`).

```text
Telco CSV -> split (Phase 1.1) -> TRAIN customers
   |                                   |
   |  (A) CLUSTERING - attributes only |  (B) PROFILING - Phase 4 outputs, AFTER clustering
   |  features -> impute -> scale ->   |  locked Phase 2 probabilities -> BusinessEngine.profile_frame
   |  K selection -> K-Means -> canonical segment ids -> nearest-centroid assignment
   +------------------> segment_id per customer <-----------------+
                              -> SegmentProfile (aggregates, name, priority, strategy)
```

## 1. Two separate steps (leakage control)
**Clustering** (`features.py`, `clustering.py`) sees customer attributes only. It never receives the churn target, the
model's probability, or any Phase 4 output, and these modules cannot import `ml.business`, `ml.explainability`, or the
model artifact (guarded by an AST test). **Profiling** (`profiling.py`, `engine.py`) runs afterwards and uses churn
probability, CLV, value at risk and ENB to *describe* clusters that already exist. Profiling never feeds back into
clustering. Proof on the real data: scrambling the churn labels and replacing the probabilities with noise leaves the
centroids and every assignment identical (only the profile numbers change).

## 2. Clustering features (explicit, from `configs/segmentation.yaml: features`)
| Feature | Source |
|---|---|
| `tenure`, `MonthlyCharges`, `TotalCharges` | raw columns |
| `service_count` | Phase 1 `FeatureEngineer` (number of subscribed services) |
| `contract_risk` | Phase 1 `FeatureEngineer` (ordinal contract-commitment prior 2/1/0 from `features.yaml`, not learned from the target) |

**Excluded:** the churn target; churn probability, risk band, CLV, value at risk, ENB, decision, recommended action
(model- or business-derived); the customer id; any validation/test information. The builder reads only the columns it
needs, so a target column present in the frame cannot reach the clustering, and the dataset target/id plus the
configured `forbidden` list are refused at configuration time (case-insensitive). CLV is deliberately **not** a
clustering feature: it is a business output and mostly redundant with monthly charges x contract.

## 3. Preprocessing and K-Means (all configurable)
Imputation (`median`|`mean`; `TotalCharges` is blank for tenure-0 customers) -> scaling (`standard`|`minmax`|`none`) ->
`KMeans(init, n_init, max_iter, tol, algorithm, random_state)`. Defaults: median, standard, `k-means++`, `n_init=10`,
`max_iter=300`. Everything is **fitted on the TRAIN split only**. `seed: null` inherits `training.yaml` seed (42).

## 4. Choosing K
Every candidate K (2-8) is scored by **silhouette** (plus inertia, Calinski-Harabasz, Davies-Bouldin as reported
metrics) and its smallest-cluster share. A K is *eligible* only if it lies in `[min_k, max_k]` (3-6) and its smallest
cluster holds >= `min_cluster_share` (5%). `method: silhouette` picks the highest silhouette among eligible K (ties ->
smaller K); `method: fixed` uses `fixed_k`. The unconstrained silhouette optimum is always reported. **The
mathematically best K is not automatically the best business segmentation**: on Telco K=2 has the highest silhouette
(0.416) but splits customers into two groups too coarse to act on, so the business range excludes it. Real run:

| K | silhouette | min cluster | inertia | Calinski-Harabasz | Davies-Bouldin | eligible |
|---|---|---|---|---|---|---|
| 2 | 0.4160 | 34.5% | 13222 | 4257 | 0.966 | no (outside 3-6) |
| **3** | **0.4072** | 18.4% | 9180 | 4149 | 0.894 | **yes, selected** |
| 4 | 0.3767 | 16.4% | 6785 | 4321 | 0.911 | yes |
| 5 | 0.3583 | 15.3% | 5567 | 4219 | 0.958 | yes |
| 6 | 0.3560 | 12.1% | 4912 | 3955 | 1.036 | yes |
| 7 / 8 | 0.3286 / 0.3351 | 10.4% / 8.6% | | | | no (outside 3-6) |

Silhouette decreases with K here, so the rule lands on the smallest eligible K. Set `fixed_k` (e.g. 4) if you want
finer groups; the profiles, naming and strategy adapt automatically.

## 5. Segment ids, label permutation and determinism
K-Means label numbers are arbitrary. After fitting, centroids are put in a **canonical order** (lexicographic on the
scaled coordinates, rounded to 6 decimals), a pure function of the centroid *set*; `segment_id` = position in that order.
`raw_label_to_segment` records the permutation (on Telco, seeds 0 and 1 give different raw orders and identical
segment ids). Assignment is plain nearest-centroid (ties -> lowest id), equal to `KMeans.predict` through the mapping.
**Names never depend on ids** (section 7), and `clusterings_equivalent` / adjusted Rand index compare partitions up to
relabelling. Same data + config + seed -> identical centroids, assignments and profiles (tested). Other seeds can reach a
marginally different local optimum (ARI >= 0.995 on Telco), which is not a bug but is why the seed is fixed.

## 6. Segment profile (one per segment; `SegmentProfile`)
`segment_id`, `segment_name`, `customer_count`, `customer_pct`, `avg_tenure`, `avg_monthly_charges`,
`avg_total_charges` (blank values ignored), `avg_churn_probability`, `avg_clv`, `total_clv`, `total_value_at_risk`,
`avg_enb`, `total_enb`, `intervention_rate`, `intervention_count`, `risk_band` (Phase 4 band of the average
probability), `priority_score/rank/tier`, `strategy`. Every business number is a sum/mean/count over
`CustomerBusinessProfile` objects from `BusinessEngine.profile_frame`; **CLV, ENB and decisions are not recomputed in
Phase 5** (guarded by an AST/token test and an independent recomputation from the CSV in the integration tests).
`avg_enb`/`total_enb` use the Phase 4 `expected_net_benefit` of the *recommended* action, which is 0 for customers
Phase 4 does not treat; `intervention_rate` is the share with decision `INTERVENE`.

## 7. Deterministic segment names (`naming:` in config)
`<Value> / <Risk>` from measured averages: **value** = segment avg CLV / portfolio avg CLV (>= 1.15 High, <= 0.85 Low,
else Mid); **risk** = segment avg churn probability (>= the locked model threshold, `model_threshold` sentinel, High
Risk; <= 0.20 Stable; else Moderate Risk). Identical names are disambiguated by tenure vs portfolio (`New` <= 0.85,
`Established` >= 1.15, else `Mid-Tenure`), then by a stable rank of measured averages (`#1`, `#2`, ... by avg CLV, then
tenure, then probability), never by cluster id. The four-name example list is illustrative only: names come from the
actual profile, and tests verify they follow the measured values and survive id permutation.

## 8. Priority (`priority:` in config)
```text
priority_score = sum(weight_m * metric_m) / sum(weight_m)        every metric_m in [0, 1]
  value_at_risk_share    0.40   segment value at risk / portfolio value at risk
  total_enb_share        0.30   segment total ENB / portfolio total ENB   (0 for all if the portfolio total <= 0)
  avg_churn_probability  0.20
  intervention_rate      0.10   share of the segment Phase 4 would treat
tiers: HIGH >= 0.30, MEDIUM >= 0.15, LOW >= 0
```
Weights and tier cut-offs are **illustrative policy choices**, not learned; replace them in YAML. Rank 1 = highest
score (ties: larger value at risk, then lower id). Note config overrides are deep-merged, so to put weight on one metric
set the others to 0 explicitly.

## 9. Retention strategy (reuse of Phase 4)
No second retention engine. The segment strategy is the Phase 4 `recommended_action_id` mix among the segment's
`INTERVENE` customers: `primary_action_id` = most frequent (ties: larger total ENB, then id), `action_mix`,
`intervention_count`, and a summary sentence with the "not a causal estimate" wording. A segment with no treated
customers gets `no_action`. Change `configs/business.yaml` (disable an action, change costs or the policy) and the
strategies change with it (tested: disabling `discount_offer` moves the segment to `priority_support`, which Phase 4
itself picks).

## 10. Customer assignment
`CustomerAssignment`: `customer_id`, `segment_id`, `segment_name`, `distance_to_centroid`. The distance is a Euclidean
**clustering distance** in scaled feature space (>= 0, not bounded by 1); it is **not a probability** and there are no
segment probabilities. `assign_customers` assigns new customers using the artifact and its segment catalog.

## 11. Segmentation artifact
`models/trichurn_segmentation_v5.0.0.joblib` + `.metadata.json` (git-ignored like the Phase 2 model). Bundle: fitted
preprocessing pipeline, canonical centroids, feature names, the `KMeans` object, metadata. Metadata: `kind`,
`model_version`, UTC time, `random_state`, `selected_k` and the full K evaluation, feature list and count, exclusion
policy, preprocessing (imputation/scaling/steps), K-Means parameters, centroids in original units, training info
(`fit_split: train`, `uses_target/uses_churn_probability/uses_validation/uses_test: false`, inertia, iterations),
dataset path (repo-relative), version hash and split sizes, the full configuration, the **segment catalog** (id, name,
count, priority), profiling provenance (SHA-256 of the business configuration and of the churn artifact used) and
library versions. The sidecar adds `artifact_sha256`. `load_verified_segmentation_artifact` hashes the bytes, compares
with the sidecar, then deserialises those same bytes, and cross-checks embedded vs sidecar metadata and the bundle kind
(`ArtifactIntegrityError` otherwise). Re-running produces identical centroids, assignments and profiles, but not byte-identical files (the metadata embeds a `trained_at` timestamp, so the SHA-256 differs per run; the integrity check always uses the sidecar written with that file). It never touches the Phase 2 churn artifact (different name; byte-identity
asserted before/after in tests and in the script).

## 12. Real result (`python scripts/run_phase5.py`; 4,929 TRAIN customers, locked model, threshold 0.34, seed 42, K=3)
| # | Segment | Customers | Avg tenure | Avg monthly | Avg churn p | Avg CLV | Total VaR | Avg ENB | Intervention | Tier (score) | Phase 4 action |
|---|---|---|---|---|---|---|---|---|---|---|---|
| 1 | Low Value / High Risk | 2,453 (49.8%) | 12.9 | 61.55 | 0.423 | 786.90 | 890,667 | 44.91 | 54.0% | HIGH (0.656) | Discount offer |
| 2 | High Value / Stable | 1,568 (31.8%) | 56.7 | 91.37 | 0.158 | 2,343.44 | 432,007 | 13.30 | 15.5% | MEDIUM (0.223) | Discount offer |
| 3 | Low Value / Stable | 908 (18.4%) | 43.3 | 27.29 | 0.027 | 845.38 | 20,713 | 0.00 | 0.0% | LOW (0.012) | No action |

Amounts are Telco's own units (INR label). VALIDATION customers (attributes only, no outcomes) fall into the same
segments in similar shares (51.2% / 30.7% / 18.2%), a sanity check that the grouping is not a TRAIN artefact.

## 13. Limitations
* Segments are **descriptive**. They do not explain *why* customers churn and do not show that a retention action works.
  **SHAP is model explanation, not causal explanation, and what-if analysis is simulation, not causal inference**; Phase 5
  inherits both caveats because it reports Phase 4 figures.
* Business figures are estimates under configured assumptions (lifetimes, costs, success rates, policy floors); the
  priority weights, tier cut-offs and naming ratios are illustrative.
* Profiles are computed on TRAIN customers, for whom the locked model's probabilities are in-sample (the model was fitted
  on them), so segment-level churn probabilities are likely somewhat optimistic about separation compared with new customers.
  No labels are used by Phase 5 itself.
* Only three raw attributes plus two engineered counts drive the clusters; K-Means assumes roughly spherical clusters and
  is sensitive to scaling and local optima (seed fixed; `n_init=10`). Silhouette is a geometric criterion, not a business one.
* The single Telco snapshot has no history, so segment drift/stability over time is out of scope (monitoring is a later phase).
