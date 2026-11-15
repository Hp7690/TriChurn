"""Parse and validate ``configs/segmentation.yaml`` into frozen typed config objects."""
from __future__ import annotations

import math
from pathlib import Path
from typing import Any

from ml.config import CONFIG_DIR, load_config
from ml.errors import SegmentationConfigError
from ml.segmentation.schemas import (
    IMPUTATIONS,
    K_METHODS,
    MODEL_THRESHOLD,
    PRIORITY_METRICS,
    REPORT_METRICS,
    SCALINGS,
    FeatureSetConfig,
    KMeansConfig,
    KSelectionConfig,
    NamingConfig,
    PriorityConfig,
    PriorityTier,
    SegmentationConfig,
)

KMEANS_INITS = ("k-means++", "random")
KMEANS_ALGORITHMS = ("lloyd", "elkan")


def _need(section: Any, key: str, where: str) -> Any:
    if not isinstance(section, dict) or key not in section:
        raise SegmentationConfigError(f"Segmentation config is missing '{where}.{key}'.")
    return section[key]


def _number(value: Any, name: str, *, lo: float | None = None, hi: float | None = None) -> float:
    if isinstance(value, bool) or not isinstance(value, int | float) or not math.isfinite(value):
        raise SegmentationConfigError(f"{name} must be a finite number, got {value!r}.")
    if lo is not None and value < lo:
        raise SegmentationConfigError(f"{name} must be >= {lo}, got {value}.")
    if hi is not None and value > hi:
        raise SegmentationConfigError(f"{name} must be <= {hi}, got {value}.")
    return float(value)


def _integer(value: Any, name: str, *, lo: int) -> int:
    if isinstance(value, bool) or not isinstance(value, int):
        raise SegmentationConfigError(f"{name} must be an integer, got {value!r}.")
    if value < lo:
        raise SegmentationConfigError(f"{name} must be >= {lo}, got {value}.")
    return value


def _choice(value: Any, options: tuple[str, ...], name: str) -> str:
    if value not in options:
        raise SegmentationConfigError(f"{name} must be one of {options}, got {value!r}.")
    return value


def _names(value: Any, name: str) -> tuple[str, ...]:
    if not isinstance(value, list) or not all(isinstance(v, str) and v.strip() for v in value):
        raise SegmentationConfigError(f"{name} must be a list of column names.")
    if len(set(value)) != len(value):
        raise SegmentationConfigError(f"{name} contains duplicates.")
    return tuple(value)


def _parse_features(raw: dict) -> FeatureSetConfig:
    cfg = FeatureSetConfig(numeric=_names(_need(raw, "numeric", "features"), "features.numeric"),
                           engineered=_names(_need(raw, "engineered", "features"), "features.engineered"),
                           forbidden=tuple(f.lower() for f in _names(_need(raw, "forbidden", "features"),
                                                                    "features.forbidden")))
    if not cfg.all:
        raise SegmentationConfigError("features must list at least one clustering feature.")
    if len(set(cfg.all)) != len(cfg.all):
        raise SegmentationConfigError("A clustering feature is listed twice across numeric/engineered.")
    banned = [f for f in cfg.all if f.lower() in cfg.forbidden]
    if banned:
        raise SegmentationConfigError(
            f"Forbidden clustering features {banned}: the target and model/business outputs may not cluster customers.")
    return cfg


def _parse_kmeans(raw: dict) -> KMeansConfig:
    return KMeansConfig(
        init=_choice(_need(raw, "init", "kmeans"), KMEANS_INITS, "kmeans.init"),
        n_init=_integer(_need(raw, "n_init", "kmeans"), "kmeans.n_init", lo=1),
        max_iter=_integer(_need(raw, "max_iter", "kmeans"), "kmeans.max_iter", lo=1),
        tol=_number(_need(raw, "tol", "kmeans"), "kmeans.tol", lo=0.0),
        algorithm=_choice(_need(raw, "algorithm", "kmeans"), KMEANS_ALGORITHMS, "kmeans.algorithm"))


def _parse_k_selection(raw: dict) -> KSelectionConfig:
    cands = _need(raw, "candidates", "k_selection")
    if not isinstance(cands, list) or not cands:
        raise SegmentationConfigError("k_selection.candidates must be a non-empty list of integers.")
    cands = sorted({_integer(c, "k_selection.candidates[]", lo=2) for c in cands})
    method = _choice(_need(raw, "method", "k_selection"), K_METHODS, "k_selection.method")
    min_k = _integer(_need(raw, "min_k", "k_selection"), "k_selection.min_k", lo=2)
    max_k = _integer(_need(raw, "max_k", "k_selection"), "k_selection.max_k", lo=2)
    if min_k > max_k:
        raise SegmentationConfigError("k_selection.min_k must be <= max_k.")
    fixed = raw.get("fixed_k")
    if method == "fixed":
        if fixed is None:
            raise SegmentationConfigError("k_selection.method is 'fixed' but fixed_k is not set.")
        fixed = _integer(fixed, "k_selection.fixed_k", lo=2)
        if fixed not in cands:
            raise SegmentationConfigError(f"k_selection.fixed_k={fixed} must be one of the candidates {cands}.")
    sample = raw.get("silhouette_sample_size")
    metrics = tuple(_choice(m, REPORT_METRICS, "k_selection.report_metrics[]")
                    for m in _need(raw, "report_metrics", "k_selection"))
    return KSelectionConfig(tuple(cands), method, fixed, min_k, max_k,
                            _number(_need(raw, "min_cluster_share", "k_selection"),
                                    "k_selection.min_cluster_share", lo=0.0, hi=0.5),
                            None if sample is None else _integer(sample, "k_selection.silhouette_sample_size", lo=10),
                            metrics)


def _parse_naming(raw: dict) -> NamingConfig:
    v, r, t = (_need(raw, s, "naming") for s in ("value", "risk", "tenure"))
    high = _need(r, "high_min_probability", "naming.risk")
    high = high if high == MODEL_THRESHOLD else _number(high, "naming.risk.high_min_probability", lo=0.0, hi=1.0)
    cfg = NamingConfig(
        _number(_need(v, "high_min_ratio", "naming.value"), "naming.value.high_min_ratio", lo=0.0),
        _number(_need(v, "low_max_ratio", "naming.value"), "naming.value.low_max_ratio", lo=0.0),
        high,
        _number(_need(r, "stable_max_probability", "naming.risk"), "naming.risk.stable_max_probability",
                lo=0.0, hi=1.0),
        _number(_need(t, "established_min_ratio", "naming.tenure"), "naming.tenure.established_min_ratio", lo=0.0),
        _number(_need(t, "new_max_ratio", "naming.tenure"), "naming.tenure.new_max_ratio", lo=0.0))
    if (cfg.value_low_max_ratio > cfg.value_high_min_ratio
            or cfg.tenure_new_max_ratio > cfg.tenure_established_min_ratio):
        raise SegmentationConfigError("naming low/new ratios must not exceed the high/established ratios.")
    if not isinstance(high, str) and cfg.risk_stable_max_probability > high:
        raise SegmentationConfigError("naming.risk.stable_max_probability must not exceed high_min_probability.")
    return cfg


def _parse_priority(raw: dict) -> PriorityConfig:
    weights = _need(raw, "weights", "priority")
    unknown = set(weights) - set(PRIORITY_METRICS)
    if unknown or not weights:
        raise SegmentationConfigError(
            f"priority.weights must use metrics from {PRIORITY_METRICS}; got {sorted(weights)}.")
    w = {k: _number(v, f"priority.weights.{k}", lo=0.0) for k, v in weights.items()}
    if sum(w.values()) <= 0:
        raise SegmentationConfigError("priority.weights must contain at least one positive weight.")
    tiers = tuple(PriorityTier(str(_need(t, "name", "priority.tiers")),
                               _number(_need(t, "min_score", "priority.tiers"), "priority.tiers.min_score",
                                       lo=0.0, hi=1.0))
                  for t in _need(raw, "tiers", "priority"))
    mins = [t.min_score for t in tiers]
    if not tiers or mins[-1] != 0.0 or any(a <= b for a, b in zip(mins[:-1], mins[1:], strict=True)):
        raise SegmentationConfigError("priority.tiers must have strictly descending min_score ending at 0.")
    if len({t.name for t in tiers}) != len(tiers):
        raise SegmentationConfigError("priority.tiers names must be unique.")
    return PriorityConfig(w, tiers)


def parse_segmentation_config(raw: dict) -> SegmentationConfig:
    """Validate a raw mapping (as loaded from YAML) into a ``SegmentationConfig``."""
    art, rep = _need(raw, "artifact", "segmentation"), _need(raw, "report", "segmentation")
    seed = raw.get("seed")
    return SegmentationConfig(
        seed=None if seed is None else _integer(seed, "seed", lo=0),
        model_version=str(_need(raw, "model_version", "segmentation")),
        features=_parse_features(_need(raw, "features", "segmentation")),
        imputation=_choice(_need(raw, "imputation", "segmentation"), IMPUTATIONS, "imputation"),
        scaling=_choice(_need(raw, "scaling", "segmentation"), SCALINGS, "scaling"),
        kmeans=_parse_kmeans(_need(raw, "kmeans", "segmentation")),
        k_selection=_parse_k_selection(_need(raw, "k_selection", "segmentation")),
        naming=_parse_naming(_need(raw, "naming", "segmentation")),
        priority=_parse_priority(_need(raw, "priority", "segmentation")),
        artifact_dir=str(_need(art, "dir", "artifact")), artifact_name=str(_need(art, "name", "artifact")),
        report_path=str(_need(rep, "path", "report")))


def load_segmentation_config(overrides: dict[str, Any] | None = None, config_dir: Path = CONFIG_DIR
                             ) -> SegmentationConfig:
    return parse_segmentation_config(load_config("segmentation", overrides, config_dir))


def resolve_seed(cfg: SegmentationConfig, training_cfg: dict) -> int:
    """``seed: null`` inherits the project seed (single source of truth, as in Phase 2)."""
    return int(training_cfg["seed"] if cfg.seed is None else cfg.seed)
