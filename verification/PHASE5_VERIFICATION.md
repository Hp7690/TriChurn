# Phase 5 verification evidence (customer segmentation and segment intelligence)

Status: **PASS** (Linux, Python 3.12.3, scikit-learn as installed from requirements.txt; real IBM Telco data, 7,043 rows).
This package is the project exactly as supplied in `trichurn_phase5.zip`; no existing file was modified.
Files under `verification/` are the only additions.

## Results
| Check | Result |
|---|---|
| Phase 5 tests (4 unit files + real-data integration) | 116 passed, 0 failed, 0 skipped |
| Phase 4 tests (unit + real-data integration) | 354 passed, 0 failed, 0 skipped |
| Full repository (Phases 1-5) | 663 passed, 0 failed, 0 skipped, 0 errors |
| `ruff check .` | All checks passed |
| `python scripts/run_phase5.py` (real data) | exit 0; K=3; 4,929 TRAIN customers; seed 42 |
| Two runs | identical stdout and identical report JSON (artifact SHA differs by design: `trained_at` timestamp) |
| Phase 2 churn artifact SHA-256 | unchanged: db399a55f650c6681e1caaf52257f909777e2c5fada3af5911370ddf5b8ff1ad |
| Shipped segmentation artifact SHA-256 | 38423c9cf19b05aa35b72acd44ea3a8af4c3775a1e6cf2bb739ee1972dc05927 (verified load; assignments and centroids equal a fresh fit) |

## Independent checks (verification/*.py, run with PYTHONPATH=. from the project root; require ml/data/raw/telco_churn.csv via `make data`)
* Leakage isolation: scrambled churn labels + random probabilities -> identical centroids and assignments; fitting without the target column -> identical assignments.
* Artifact integrity: one flipped byte rejected (SHA-256 mismatch); corrupted sidecar digest rejected.
* Aggregates: customer count, avg churn probability, avg CLV, total value at risk, total ENB, intervention count and avg tenure recomputed from the Phase 4 profiles for all 3 segments: all match.
* Configuration sensitivity: fixed K, seed, K-selection method, priority weights and Phase 4 action config each change the output as documented; disabling `discount_offer` changes strategies but not clusters.
* TEST split: only `len(parts.test)` is used (split-size metadata); no test rows are read.

## Not included / caveats
* `ml/data/raw/telco_churn.csv` is not packaged (git-ignored by design; it was not in the supplied zip). Restore with `python scripts/download_telco.py` or `make data`; its SHA-256 prefix 16320c9c1ec7 matches the dataset version recorded in the Phase 2 artifact.
* Verified on Linux/Python 3.12 only. Earlier failures reported on Windows/Python 3.13 (an absolute-path test and three Phase 2 isolation variants) did not reproduce here and are not addressed by this package.
* Segment name vs risk band can differ (e.g. avg probability 0.423 is "High Risk" by the model threshold 0.34 but band MEDIUM); both follow their documented rules.
* Profiles are computed on TRAIN customers (in-sample for the locked model); segments are descriptive, not causal.
