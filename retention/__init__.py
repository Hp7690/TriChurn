"""TriChurn Phase 9 - Advanced Retention Intelligence (framework-free domain package).

Reuses, and never modifies, the locked Phase 1-5 implementation:
  * Phase 2 churn model + Phase 4 business engine (CLV, value at risk, ENB, actions, eligibility, decision),
  * Phase 5 segmentation (nearest-centroid assignment only).

Everything here is an ESTIMATE under configured assumptions or an OBSERVATION recorded by users. Nothing is causal
uplift: no treatment/control data exists in the project.
"""
from __future__ import annotations

__version__ = "9.0.0"

ESTIMATE_NOTE = (
    "Estimates are computed from the locked Phase 2 churn probabilities and the ASSUMED action costs and success "
    "rates in configs/business.yaml. They are not measured campaign results and not causal uplift estimates."
)
SCORE_NOTE = (
    "The priority score (0-100) is a transparent heuristic: a weighted blend of percentile ranks. It is not a "
    "probability and has not been statistically validated against campaign outcomes."
)
