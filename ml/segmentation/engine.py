"""Phase 5 entry points. Clustering and profiling are separate steps; only profiling touches business outputs.

``fit_segmentation`` (clustering.py) sees TRAIN customer attributes only. ``run_segmentation`` here then profiles the
same customers with the ACTUAL Phase 4 ``BusinessEngine`` (probabilities come from the locked Phase 2 artifact).
"""
from __future__ import annotations

from collections.abc import Mapping, Sequence
from dataclasses import dataclass

import numpy as np
import pandas as pd

from ml.business import BusinessEngine, CustomerBusinessProfile
from ml.errors import SegmentationInputError
from ml.pipelines.ingestion import DatasetSpec
from ml.segmentation.clustering import SegmentationModel, fit_segmentation
from ml.segmentation.config import resolve_seed
from ml.segmentation.profiling import build_assignments, profile_segments
from ml.segmentation.schemas import (
    CustomerAssignment,
    KSelection,
    SegmentationConfig,
    SegmentProfile,
)


@dataclass
class SegmentationResult:
    model: SegmentationModel
    selection: KSelection | None
    seed: int
    profiles: list[SegmentProfile]
    assignments: list[CustomerAssignment]
    business_profiles: list[CustomerBusinessProfile]
    segment_ids: np.ndarray

    def to_dict(self) -> dict:
        return {"selected_k": self.model.k, "seed": self.seed,
                "k_selection": None if self.selection is None else self.selection.to_dict(),
                "segments": [p.to_dict() for p in self.profiles],
                "assignments": [a.to_dict() for a in self.assignments]}


def run_segmentation(
    train_df: pd.DataFrame, probabilities: Sequence[float], engine: BusinessEngine, spec: DatasetSpec,
    cfg: SegmentationConfig, features_cfg: dict, training_cfg: dict, k: int | None = None,
) -> SegmentationResult:
    """Cluster TRAIN customers (attributes only), then profile them with Phase 4 outputs.

    ``probabilities`` are the locked model's churn probabilities for ``train_df`` rows; they are passed to the Phase 4
    engine and are never given to the clustering step."""
    seed = resolve_seed(cfg, training_cfg)
    model, selection = fit_segmentation(train_df, spec, cfg, features_cfg, seed, k)     # no probabilities in sight
    business_profiles = engine.profile_frame(train_df, probabilities, spec.id_column)    # Phase 4
    ids, dist = model.assign(train_df)
    profiles = profile_segments(train_df, ids, business_profiles, engine.config, features_cfg, cfg.naming,
                                cfg.priority, engine.model_threshold, spec.id_column)
    assignments = build_assignments(train_df[spec.id_column].tolist(), ids, dist, profiles)
    return SegmentationResult(model, selection, seed, profiles, assignments, business_profiles, ids)


def assign_customers(model: SegmentationModel, names: Mapping[int, str], customers: pd.DataFrame,
                     id_column: str | None = None) -> list[CustomerAssignment]:
    """Assign NEW customers (e.g. validation rows) to the fitted segments; ``names`` = artifact segment catalog."""
    if id_column is not None and id_column not in customers.columns:
        raise SegmentationInputError(f"id column '{id_column}' is not in the customer frame.")
    ids, dist = model.assign(customers)
    unknown = set(ids.tolist()) - set(names)
    if unknown:
        raise SegmentationInputError(f"Segment names are missing for ids {sorted(unknown)}.")
    cust = customers[id_column].tolist() if id_column else [None] * len(customers)
    return [CustomerAssignment(None if c is None else str(c), int(s), names[int(s)], float(d))
            for c, s, d in zip(cust, ids, dist, strict=True)]
