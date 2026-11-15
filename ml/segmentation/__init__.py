"""Phase 5 - customer segmentation and segment intelligence.

K-Means clustering of customer attributes (no target, no model output, TRAIN only), then segment profiles built from the
ACTUAL Phase 4 business outputs. Pure Python/sklearn: no FastAPI, no backend, no database. Segments are descriptive
groups, not causal explanations of churn.
"""
from ml.segmentation.artifact import (
    VerifiedSegmentation,
    build_metadata,
    fingerprint,
    load_verified_segmentation_artifact,
    save_segmentation_artifact,
)
from ml.segmentation.clustering import (
    SegmentationModel,
    canonical_order,
    clusterings_equivalent,
    evaluate_k_candidates,
    fit_segmentation,
    select_k,
)
from ml.segmentation.config import load_segmentation_config, parse_segmentation_config, resolve_seed
from ml.segmentation.engine import SegmentationResult, assign_customers, run_segmentation
from ml.segmentation.features import SegmentationFeatureBuilder, build_preprocessor, validate_feature_set
from ml.segmentation.profiling import build_assignments, profile_segments
from ml.segmentation.schemas import (
    CustomerAssignment,
    KCandidate,
    KSelection,
    SegmentationConfig,
    SegmentProfile,
    SegmentStrategy,
)

__all__ = [
    "CustomerAssignment", "KCandidate", "KSelection", "SegmentProfile", "SegmentStrategy", "SegmentationConfig",
    "SegmentationFeatureBuilder", "SegmentationModel", "SegmentationResult", "VerifiedSegmentation",
    "assign_customers", "build_assignments", "build_metadata", "build_preprocessor", "canonical_order",
    "clusterings_equivalent", "evaluate_k_candidates", "fingerprint", "fit_segmentation",
    "load_segmentation_config", "load_verified_segmentation_artifact", "parse_segmentation_config",
    "profile_segments", "resolve_seed", "run_segmentation", "save_segmentation_artifact", "select_k",
    "validate_feature_set",
]
