"""Typed, immutable data structures for Phase 5. Construction-time invariants and ``to_dict`` only."""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

MODEL_THRESHOLD = "model_threshold"      # naming.risk.high_min_probability sentinel (same convention as Phase 4)
SCALINGS = ("standard", "minmax", "none")
IMPUTATIONS = ("median", "mean")
K_METHODS = ("silhouette", "fixed")
REPORT_METRICS = ("inertia", "calinski_harabasz", "davies_bouldin")
PRIORITY_METRICS = ("value_at_risk_share", "total_enb_share", "avg_churn_probability", "intervention_rate")

PROFILING_NOTE = (
    "Segments are descriptive groups found by unsupervised clustering of customer attributes. Churn probability, CLV, "
    "value at risk and ENB describe each segment under the Phase 2 model and the configured Phase 4 assumptions; they "
    "do not show that a segment's characteristics cause churn or that a retention action will work."
)


@dataclass(frozen=True)
class FeatureSetConfig:
    numeric: tuple[str, ...]
    engineered: tuple[str, ...]
    forbidden: tuple[str, ...]

    @property
    def all(self) -> tuple[str, ...]:
        return self.numeric + self.engineered


@dataclass(frozen=True)
class KMeansConfig:
    init: str
    n_init: int
    max_iter: int
    tol: float
    algorithm: str


@dataclass(frozen=True)
class KSelectionConfig:
    candidates: tuple[int, ...]
    method: str
    fixed_k: int | None
    min_k: int
    max_k: int
    min_cluster_share: float
    silhouette_sample_size: int | None
    report_metrics: tuple[str, ...]


@dataclass(frozen=True)
class NamingConfig:
    value_high_min_ratio: float
    value_low_max_ratio: float
    risk_high_min_probability: float | str      # number or MODEL_THRESHOLD
    risk_stable_max_probability: float
    tenure_established_min_ratio: float
    tenure_new_max_ratio: float


@dataclass(frozen=True)
class PriorityTier:
    name: str
    min_score: float


@dataclass(frozen=True)
class PriorityConfig:
    weights: dict[str, float]
    tiers: tuple[PriorityTier, ...]


@dataclass(frozen=True)
class SegmentationConfig:
    seed: int | None
    model_version: str
    features: FeatureSetConfig
    imputation: str
    scaling: str
    kmeans: KMeansConfig
    k_selection: KSelectionConfig
    naming: NamingConfig
    priority: PriorityConfig
    artifact_dir: str
    artifact_name: str
    report_path: str


@dataclass(frozen=True)
class KCandidate:
    k: int
    silhouette: float
    min_cluster_share: float
    eligible: bool
    ineligible_reason: str | None
    extra: dict[str, float] = field(default_factory=dict)       # inertia / calinski_harabasz / davies_bouldin

    def to_dict(self) -> dict[str, Any]:
        return {"k": self.k, "silhouette": self.silhouette, "min_cluster_share": self.min_cluster_share,
                "eligible": self.eligible, "ineligible_reason": self.ineligible_reason, **self.extra}


@dataclass(frozen=True)
class KSelection:
    selected_k: int
    method: str
    rationale: str
    candidates: tuple[KCandidate, ...]
    best_silhouette_k: int          # the unconstrained mathematical optimum, reported for transparency

    def to_dict(self) -> dict[str, Any]:
        return {"selected_k": self.selected_k, "method": self.method, "rationale": self.rationale,
                "best_silhouette_k_unconstrained": self.best_silhouette_k,
                "candidates": [c.to_dict() for c in self.candidates]}


@dataclass(frozen=True)
class CustomerAssignment:
    """Cluster membership; ``distance_to_centroid`` is a Euclidean clustering distance, NOT a probability."""
    customer_id: str | None
    segment_id: int
    segment_name: str
    distance_to_centroid: float

    def to_dict(self) -> dict[str, Any]:
        return {"customer_id": self.customer_id, "segment_id": self.segment_id, "segment_name": self.segment_name,
                "distance_to_centroid": self.distance_to_centroid}


@dataclass(frozen=True)
class SegmentStrategy:
    """Derived entirely from Phase 4 decisions for the segment's customers; no separate retention logic."""
    primary_action_id: str                   # most frequent Phase 4 action among INTERVENE customers, else no_action
    primary_action_name: str
    action_mix: dict[str, int]               # Phase 4 recommended_action_id -> customers (INTERVENE only)
    intervention_count: int
    summary: str

    def to_dict(self) -> dict[str, Any]:
        return {"primary_action_id": self.primary_action_id, "primary_action_name": self.primary_action_name,
                "action_mix": dict(self.action_mix), "intervention_count": self.intervention_count,
                "summary": self.summary}


@dataclass(frozen=True)
class SegmentProfile:
    segment_id: int
    segment_name: str
    value_label: str
    risk_label: str
    customer_count: int
    customer_pct: float
    avg_tenure: float
    avg_monthly_charges: float
    avg_total_charges: float
    avg_churn_probability: float
    avg_clv: float
    total_clv: float
    total_value_at_risk: float
    avg_enb: float                      # mean of Phase 4 expected_net_benefit (0 for customers with no intervention)
    total_enb: float
    intervention_rate: float
    intervention_count: int
    risk_band: str                      # Phase 4 risk band of the segment's average churn probability
    priority_score: float
    priority_rank: int
    priority_tier: str
    strategy: SegmentStrategy

    def to_dict(self) -> dict[str, Any]:
        d = {k: v for k, v in self.__dict__.items() if k != "strategy"}
        d["strategy"] = self.strategy.to_dict()
        return d
