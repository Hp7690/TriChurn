"""Phase 2 - decision-threshold optimisation (VALIDATION only).

The input is deliberately just ``(y_val, p_val)``: the (calibrated) validation probabilities and labels.
The function has no way to receive features, a model, or test data.
"""
from __future__ import annotations

from dataclasses import dataclass

import numpy as np

METRICS = ("f1", "f_beta", "recall_at_precision")


@dataclass
class ThresholdResult:
    threshold: float
    metric: str
    objective: float           # value of the optimised objective at `threshold` (validation)
    precision: float
    recall: float
    f1: float
    source: str                # "optimized" | "configured"
    n_tied: int                # grid points tied for the optimum (the median one is used)
    curve: list[dict]          # coarse precision/recall/F1 curve for reporting

    def to_dict(self) -> dict:
        return {"threshold": self.threshold, "metric": self.metric, "objective": self.objective,
                "precision": self.precision, "recall": self.recall, "f1": self.f1, "source": self.source,
                "n_tied": self.n_tied, "curve": self.curve}


def threshold_grid(grid_cfg: dict) -> np.ndarray:
    g = np.arange(grid_cfg["start"], grid_cfg["stop"] + grid_cfg["step"] / 2, grid_cfg["step"])
    return np.round(g, 6)


def precision_recall_at(y_true, p, thresholds) -> tuple[np.ndarray, np.ndarray, np.ndarray]:
    """Vectorised precision / recall / F1 over thresholds (predict positive when p >= t)."""
    y = np.asarray(y_true).astype(bool)
    p = np.asarray(p, dtype=float)
    pred = p[None, :] >= np.asarray(thresholds)[:, None]
    tp = (pred & y[None, :]).sum(axis=1).astype(float)
    fp = (pred & ~y[None, :]).sum(axis=1).astype(float)
    fn = (~pred & y[None, :]).sum(axis=1).astype(float)
    prec = np.divide(tp, tp + fp, out=np.zeros_like(tp), where=(tp + fp) > 0)
    rec = np.divide(tp, tp + fn, out=np.zeros_like(tp), where=(tp + fn) > 0)
    f1 = np.divide(2 * prec * rec, prec + rec, out=np.zeros_like(tp), where=(prec + rec) > 0)
    return prec, rec, f1


def _objective(metric: str, prec, rec, th_cfg: dict) -> np.ndarray:
    if metric == "f1":
        b2 = 1.0
    elif metric == "f_beta":
        b2 = float(th_cfg.get("beta", 1.0)) ** 2
    elif metric == "recall_at_precision":
        # maximise recall subject to precision >= min_precision (infeasible thresholds are excluded)
        return np.where(prec >= th_cfg.get("min_precision", 0.5), rec, -1.0)
    else:
        raise ValueError(f"Unknown threshold metric '{metric}'. Choose from {METRICS}.")
    denom = b2 * prec + rec
    return np.divide((1 + b2) * prec * rec, denom, out=np.zeros_like(prec), where=denom > 0)


def optimize_threshold(y_val, p_val, th_cfg: dict) -> ThresholdResult:
    """Pick the decision threshold on VALIDATION. Honors ``th_cfg['override']`` (a fixed policy value)."""
    metric = th_cfg["metric"]
    grid = threshold_grid(th_cfg["grid"])
    prec, rec, f1 = precision_recall_at(y_val, p_val, grid)
    obj = _objective(metric, prec, rec, th_cfg)
    curve_idx = [i for i, t in enumerate(grid) if abs(t * 20 - round(t * 20)) < 1e-6]  # every 0.05
    curve = [{"threshold": float(grid[i]), "precision": float(prec[i]), "recall": float(rec[i]),
              "f1": float(f1[i])} for i in curve_idx]

    override = th_cfg.get("override")
    if override is not None:
        t = float(override)
        p_, r_, f_ = precision_recall_at(y_val, p_val, [t])
        o_ = _objective(metric, p_, r_, th_cfg)
        return ThresholdResult(t, metric, float(o_[0]), float(p_[0]), float(r_[0]), float(f_[0]),
                               "configured", 1, curve)

    if metric == "recall_at_precision" and obj.max() < 0:
        raise ValueError(f"No threshold on the grid reaches precision >= {th_cfg.get('min_precision', 0.5)} "
                         "on the validation set.")
    best = obj.max()
    tied = np.flatnonzero(np.isclose(obj, best, rtol=0, atol=1e-12))
    i = int(tied[len(tied) // 2])   # median of the plateau: stable and not at its edge
    return ThresholdResult(float(grid[i]), metric, float(obj[i]), float(prec[i]), float(rec[i]),
                           float(f1[i]), "optimized", int(len(tied)), curve)
