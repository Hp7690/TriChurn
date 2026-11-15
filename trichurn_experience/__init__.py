"""Phase 13 - Customer Experience & Sentiment Intelligence (additive; standard library + PyYAML only).

Only the tenure-based lifecycle proxy can run on the Telco dataset. Feedback, sentiment, complaint, NPS, CSAT and
journey analytics require real datasets and report BLOCKED_BY_MISSING_DATA until those are configured.
"""

from trichurn_experience.config import ExperienceConfig, ExperienceConfigError, load_experience_config, parse_config
from trichurn_experience.lifecycle import assign_group, compute_lifecycle
from trichurn_experience.schemas import BlockedByMissingData, DatasetKind, ModuleStatus, ValidationReport, build_schemas
from trichurn_experience.surveys import compute_csat, compute_nps
from trichurn_experience.validation import validate_content

__all__ = [
    "BlockedByMissingData",
    "DatasetKind",
    "ExperienceConfig",
    "ExperienceConfigError",
    "ModuleStatus",
    "ValidationReport",
    "assign_group",
    "build_schemas",
    "compute_csat",
    "compute_lifecycle",
    "compute_nps",
    "load_experience_config",
    "parse_config",
    "validate_content",
]
