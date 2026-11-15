"""K-Means segmentation: candidate-K evaluation, K selection, canonical label ordering, assignment.

Pure unsupervised code: nothing here imports the churn model, Phase 4, or any target. K-Means label numbers are
arbitrary (a different seed or library version can permute them), so the fitted centroids are put in a CANONICAL
order, a pure function of the centroid set (lexicographic on the scaled coordinates), and ``segment_id`` means
"position in that order". Segment NAMES are derived later from measured characteristics, never from the id.
"""
from __future__ import annotations

from dataclasses import dataclass

import numpy as np
import pandas as pd
from sklearn.cluster import KMeans
from sklearn.metrics import calinski_harabasz_score, davies_bouldin_score, silhouette_score
from sklearn.pipeline import Pipeline

from ml.errors import SegmentationConfigError, SegmentationInputError
from ml.pipelines.ingestion import DatasetSpec
from ml.segmentation.features import build_preprocessor
from ml.segmentation.schemas import KCandidate, KMeansConfig, KSelection, KSelectionConfig, SegmentationConfig

_ROUND = 6          # decimals used when ordering centroids, so float noise cannot change the order


def make_kmeans(k: int, cfg: KMeansConfig, seed: int) -> KMeans:
    return KMeans(n_clusters=k, init=cfg.init, n_init=cfg.n_init, max_iter=cfg.max_iter, tol=cfg.tol,
                  algorithm=cfg.algorithm, random_state=seed)


def canonical_order(centers: np.ndarray) -> np.ndarray:
    """Indices that sort centroids lexicographically (first feature, then second, ...). Label-permutation invariant."""
    rounded = np.round(centers, _ROUND)
    return np.lexsort(tuple(rounded[:, j] for j in reversed(range(rounded.shape[1]))))


def evaluate_k_candidates(Z: np.ndarray, sel: KSelectionConfig, kmeans_cfg: KMeansConfig, seed: int
                          ) -> tuple[KCandidate, ...]:
    """Silhouette (+ configured extra metrics) and smallest-cluster share for every candidate K."""
    n = len(Z)
    usable = [k for k in sel.candidates if k < n]
    if not usable:
        raise SegmentationInputError(f"Only {n} customers: too few for candidate K values {list(sel.candidates)}.")
    out = []
    for k in usable:
        km = make_kmeans(k, kmeans_cfg, seed).fit(Z)
        labels = km.labels_
        share = float(np.bincount(labels, minlength=k).min() / n)
        extra: dict[str, float] = {}
        if "inertia" in sel.report_metrics:
            extra["inertia"] = float(km.inertia_)
        if "calinski_harabasz" in sel.report_metrics:
            extra["calinski_harabasz"] = float(calinski_harabasz_score(Z, labels))
        if "davies_bouldin" in sel.report_metrics:
            extra["davies_bouldin"] = float(davies_bouldin_score(Z, labels))
        sil = float(silhouette_score(Z, labels, sample_size=sel.silhouette_sample_size, random_state=seed))
        reason = None
        if not sel.min_k <= k <= sel.max_k:
            reason = f"K={k} is outside the allowed business range [{sel.min_k}, {sel.max_k}]"
        elif share < sel.min_cluster_share:
            reason = f"smallest cluster holds {share:.1%} < required {sel.min_cluster_share:.1%}"
        out.append(KCandidate(k, sil, share, reason is None, reason, extra))
    return tuple(out)


def select_k(candidates: tuple[KCandidate, ...], sel: KSelectionConfig) -> KSelection:
    """Deterministic K choice. silhouette: best among ELIGIBLE K (ties -> smaller K); fixed: ``fixed_k``."""
    best_any = max(candidates, key=lambda c: (c.silhouette, -c.k)).k
    if sel.method == "fixed":
        chosen = next((c for c in candidates if c.k == sel.fixed_k), None)
        if chosen is None:
            raise SegmentationConfigError(f"fixed_k={sel.fixed_k} could not be evaluated on this data.")
        return KSelection(chosen.k, "fixed", f"K={chosen.k} was fixed in configuration (silhouette "
                          f"{chosen.silhouette:.4f}); the unconstrained silhouette optimum is K={best_any}.",
                          candidates, best_any)
    eligible = [c for c in candidates if c.eligible]
    if not eligible:
        raise SegmentationConfigError(
            "No candidate K satisfies the business constraints (min_k/max_k/min_cluster_share); relax them or use "
            "method 'fixed'.")
    chosen = max(eligible, key=lambda c: (c.silhouette, -c.k))
    note = ("" if chosen.k == best_any else
            f" The unconstrained silhouette optimum is K={best_any}, excluded by the business constraints.")
    return KSelection(chosen.k, "silhouette",
                      f"K={chosen.k} has the highest silhouette ({chosen.silhouette:.4f}) among eligible K in "
                      f"[{sel.min_k}, {sel.max_k}] with smallest cluster >= {sel.min_cluster_share:.0%}.{note}",
                      candidates, best_any)


@dataclass
class SegmentationModel:
    """Fitted preprocessing + canonically ordered centroids. Assignment is a plain nearest-centroid rule."""
    preprocessor: Pipeline
    centers: np.ndarray                 # (k, d) in the SCALED feature space, canonical order
    feature_names: list[str]
    raw_label_to_segment: np.ndarray    # sklearn K-Means label -> segment_id (documents the permutation)
    kmeans: KMeans                      # the underlying fitted estimator (provenance: inertia, iterations)

    @property
    def k(self) -> int:
        return len(self.centers)

    def transform(self, customers: pd.DataFrame) -> np.ndarray:
        return np.asarray(self.preprocessor.transform(customers), dtype="float64")

    def assign_matrix(self, Z: np.ndarray) -> tuple[np.ndarray, np.ndarray]:
        dist = np.sqrt(((Z[:, None, :] - self.centers[None, :, :]) ** 2).sum(axis=2))
        ids = dist.argmin(axis=1)                      # ties -> lowest segment_id
        return ids.astype(int), dist[np.arange(len(Z)), ids]

    def assign(self, customers: pd.DataFrame) -> tuple[np.ndarray, np.ndarray]:
        """(segment_id, Euclidean distance to its centroid in scaled space) per customer."""
        return self.assign_matrix(self.transform(customers))

    def centers_original_units(self) -> np.ndarray:
        scaler = self.preprocessor.named_steps["scale"]
        return scaler.inverse_transform(self.centers) if hasattr(scaler, "inverse_transform") else self.centers.copy()


def fit_segmentation(train_df: pd.DataFrame, spec: DatasetSpec, cfg: SegmentationConfig, features_cfg: dict,
                     seed: int, k: int | None = None) -> tuple[SegmentationModel, KSelection | None]:
    """Fit preprocessing and K-Means on TRAIN customers. ``k`` skips selection (returns ``None`` for the selection)."""
    pre = build_preprocessor(cfg, features_cfg, spec).fit(train_df)
    Z = np.asarray(pre.transform(train_df), dtype="float64")
    selection = None
    if k is None:
        selection = select_k(evaluate_k_candidates(Z, cfg.k_selection, cfg.kmeans, seed), cfg.k_selection)
        k = selection.selected_k
    return build_model(pre, Z, k, cfg, seed), selection


def build_model(pre: Pipeline, Z: np.ndarray, k: int, cfg: SegmentationConfig, seed: int) -> SegmentationModel:
    km = make_kmeans(k, cfg.kmeans, seed).fit(Z)
    order = canonical_order(km.cluster_centers_)
    raw_to_segment = np.empty(k, dtype=int)
    raw_to_segment[order] = np.arange(k)
    return SegmentationModel(pre, km.cluster_centers_[order].copy(), list(cfg.features.all), raw_to_segment, km)


def clusterings_equivalent(a: np.ndarray, b: np.ndarray) -> bool:
    """True iff two label vectors define the same partition (identical up to a relabelling of the clusters)."""
    a, b = np.asarray(a), np.asarray(b)
    if a.shape != b.shape:
        return False
    pairs = set(zip(a.tolist(), b.tolist(), strict=True))
    return len(pairs) == len(set(a.tolist())) == len(set(b.tolist()))
