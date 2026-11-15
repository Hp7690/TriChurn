"""Phase 2 - hyperparameter tuning (TRAIN only).

For each baseline model a seeded random search is run over the (small) search space in
``configs/optimization.yaml``. Every candidate is scored by stratified K-fold cross-validation of the
*full* Phase 1.1 pipeline (coerce -> engineer -> impute/scale/encode -> estimator), so every
transformer is re-fitted inside each fold. The same folds are used for every candidate.

Signature rule: nothing in this module accepts validation or test data. Only ``X_train, y_train``.
The Phase 1.1 default parameters are always evaluated as a candidate, so tuning can be compared against
(and can never silently be worse than, on CV) the baseline.
"""
from __future__ import annotations

import json
import math
import time
from dataclasses import dataclass
from typing import Any

import pandas as pd
from sklearn.model_selection import ParameterSampler

from ml.pipelines.evaluation import cross_validate_pipeline
from ml.pipelines.preprocessing import FeaturePlan, build_pipeline
from ml.pipelines.training import MODEL_NAMES, make_estimator

IMBALANCE_KEY = "imbalance"


@dataclass
class Candidate:
    """One hyperparameter configuration and its TRAIN cross-validation scores."""
    imbalance: str
    params: dict[str, Any]
    cv: dict
    is_baseline: bool = False
    rank: int = 0

    def key(self) -> str:
        return json.dumps({"imbalance": self.imbalance, "params": self.params}, sort_keys=True, default=str)

    def to_dict(self) -> dict:
        return {"rank": self.rank, "is_baseline": self.is_baseline, "imbalance": self.imbalance,
                "params": self.params, "cv": self.cv}


@dataclass
class TuningResult:
    model: str
    primary_metric: str
    n_splits: int
    seed: int
    search_space: dict
    n_candidates: int
    best: Candidate
    baseline: Candidate | None
    candidates: list[Candidate]
    seconds: float = 0.0

    def to_dict(self) -> dict:
        return {
            "model": self.model, "primary_metric": self.primary_metric, "n_splits": self.n_splits,
            "seed": self.seed, "search_space": self.search_space, "n_candidates": self.n_candidates,
            "best": self.best.to_dict(),
            "baseline": self.baseline.to_dict() if self.baseline else None,
            "candidates": [c.to_dict() for c in self.candidates],
            "seconds": round(self.seconds, 2),
        }


def grid_size(space: dict[str, list]) -> int:
    return math.prod(len(v) for v in space.values())


def sample_configs(space: dict[str, list], n_iter: int, seed: int) -> list[dict[str, Any]]:
    """Seeded sample of the search space (without replacement; the whole grid if it is small)."""
    n = min(n_iter, grid_size(space))
    return list(ParameterSampler(space, n_iter=n, random_state=seed))


def _split_config(cfg: dict[str, Any]) -> tuple[str, dict[str, Any]]:
    cfg = dict(cfg)
    imbalance = cfg.pop(IMBALANCE_KEY)
    return imbalance, cfg


def build_candidate_pipeline(model: str, imbalance: str, params: dict[str, Any], y_train: pd.Series,
                             plan: FeaturePlan, features_cfg: dict, seed: int):
    """Phase 1.1 pipeline with the estimator built by the existing ``make_estimator``."""
    est = make_estimator(model, imbalance, y_train, {"models": {model: params}}, seed)
    return build_pipeline(plan, est, features_cfg)


def baseline_configs(model: str, training_cfg: dict, opt_cfg: dict) -> list[dict[str, Any]]:
    """Phase 1.1 default parameters x every Phase 1.1 imbalance candidate."""
    base = dict(training_cfg["models"][model])
    return [{IMBALANCE_KEY: imb, **base} for imb in training_cfg["imbalance"]["candidates"]]


def tune_model(
    model: str, X_train: pd.DataFrame, y_train: pd.Series, plan: FeaturePlan,
    training_cfg: dict, features_cfg: dict, opt_cfg: dict, seed: int,
) -> TuningResult:
    """Random search + stratified CV on TRAIN. Returns every candidate, ranked, and the best."""
    if model not in MODEL_NAMES:
        raise ValueError(f"Unknown model '{model}'. Choose from {MODEL_NAMES}.")
    tcfg = opt_cfg["tuning"]
    primary, tiebreak = tcfg["primary_metric"], tcfg["tiebreak_metric"]
    n_splits = tcfg["cv"]["n_splits"]
    space = tcfg["spaces"][model]
    t0 = time.perf_counter()

    configs: list[tuple[dict[str, Any], bool]] = []
    seen: set[str] = set()

    def add(cfg: dict[str, Any], is_baseline: bool) -> None:
        imbalance, params = _split_config(cfg)
        key = json.dumps({"imbalance": imbalance, "params": params}, sort_keys=True, default=str)
        if key not in seen:
            seen.add(key)
            configs.append((cfg, is_baseline))

    if tcfg.get("include_baseline", True):
        for cfg in baseline_configs(model, training_cfg, opt_cfg):
            add(cfg, True)
    for cfg in sample_configs(space, tcfg["n_iter"][model], seed):
        add(cfg, False)

    candidates: list[Candidate] = []
    for cfg, is_baseline in configs:
        imbalance, params = _split_config(cfg)
        pipe = build_candidate_pipeline(model, imbalance, params, y_train, plan, features_cfg, seed)
        cv = cross_validate_pipeline(pipe, X_train, y_train, n_splits=n_splits, seed=seed)
        candidates.append(Candidate(imbalance, params, cv, is_baseline))

    order = sorted(range(len(candidates)),
                   key=lambda i: (-candidates[i].cv[primary]["mean"], -candidates[i].cv[tiebreak]["mean"], i))
    ranked = [candidates[i] for i in order]
    for r, c in enumerate(ranked, start=1):
        c.rank = r
    baselines = [c for c in ranked if c.is_baseline]
    return TuningResult(
        model=model, primary_metric=primary, n_splits=n_splits, seed=seed, search_space=space,
        n_candidates=len(ranked), best=ranked[0], baseline=baselines[0] if baselines else None,
        candidates=ranked, seconds=time.perf_counter() - t0,
    )


def tune_all(
    X_train: pd.DataFrame, y_train: pd.Series, plan: FeaturePlan, training_cfg: dict,
    features_cfg: dict, opt_cfg: dict, seed: int, models: list[str] | None = None,
) -> dict[str, TuningResult]:
    return {m: tune_model(m, X_train, y_train, plan, training_cfg, features_cfg, opt_cfg, seed)
            for m in (models or MODEL_NAMES)}
