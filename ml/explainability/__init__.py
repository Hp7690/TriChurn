"""Phase 3 - SHAP explainability for the locked Phase 2 model."""
from ml.explainability.feature_importance import (
    FeatureMap,
    build_feature_map,
    global_importance,
    top_negative_drivers,
    top_positive_drivers,
)
from ml.explainability.schemas import FeatureContribution, GlobalImportanceItem, LocalExplanation
from ml.explainability.shap_explainer import (
    ChurnShapExplainer,
    VerifiedArtifact,
    load_train_background,
    load_verified_artifact,
    select_background,
    validate_input,
)

__all__ = [
    "ChurnShapExplainer", "FeatureContribution", "FeatureMap", "GlobalImportanceItem", "LocalExplanation",
    "VerifiedArtifact", "build_feature_map", "global_importance", "load_train_background",
    "load_verified_artifact", "select_background", "top_negative_drivers", "top_positive_drivers",
    "validate_input",
]
