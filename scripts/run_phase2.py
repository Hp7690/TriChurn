"""Phase 2 CLI: tune, compare, calibrate, optimise the threshold, evaluate on TEST once, save the model.

    python scripts/run_phase2.py [--csv PATH] [--spec configs/datasets/telco.yaml]

Reads configs/training.yaml (split, seed) and configs/optimization.yaml (everything else).
"""
from __future__ import annotations

import argparse
import json
import sys
import warnings
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from ml.config import load_config  # noqa: E402
from ml.errors import TriChurnError  # noqa: E402
from ml.pipelines.ingestion import DatasetSpec, dataset_version, load_csv  # noqa: E402
from ml.pipelines.optimization import run_optimization  # noqa: E402
from ml.pipelines.serialization import resolve_dir  # noqa: E402

ROOT = Path(__file__).resolve().parents[1]


def _rel(path: str) -> str:
    """Repo-relative path when possible, so reports never embed machine-specific locations."""
    p = Path(path).resolve()
    try:
        return p.relative_to(ROOT).as_posix()
    except ValueError:
        return p.name


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--csv", default=str(ROOT / "ml/data/raw/telco_churn.csv"))
    ap.add_argument("--spec", default=str(ROOT / "configs/datasets/telco.yaml"))
    ap.add_argument("--out", default=None, help="report path (default: report.path in optimization.yaml)")
    args = ap.parse_args()
    warnings.filterwarnings("ignore")

    quality, training, features, opt = (load_config(n) for n in ("quality", "training", "features",
                                                                  "optimization"))
    try:
        df = load_csv(args.csv, quality["limits"]["max_file_mb"])
        rep = run_optimization(
            df, DatasetSpec.from_yaml(args.spec), quality, training, features, opt,
            dataset_info={"path": _rel(args.csv), "version": dataset_version(args.csv), "rows": len(df)},
            artifact_dir=opt["artifacts"]["dir"])
    except TriChurnError as exc:
        print(f"ERROR: {exc}")
        return 1

    d = rep.to_dict()
    print(f"Splits: {d['split_sizes']}   seed={d['configuration']['seed']}")
    print(f"\n== TUNING (TRAIN CV, primary metric: {opt['tuning']['primary_metric']}) ==")
    for m, t in d["tuning"].items():
        b, base = t["best"], t["baseline"]
        print(f"{m:20s} candidates={t['n_candidates']:3d} best CV PR-AUC={b['cv']['pr_auc']['mean']:.4f} "
              f"(baseline {base['cv']['pr_auc']['mean']:.4f})  imbalance={b['imbalance']}  params={b['params']}")
    print("\n== MODEL COMPARISON (tuned config; CV on TRAIN | VALIDATION @0.5) ==")
    print(f"{'model':20s}{'CV PR':>8s}{'CV ROC':>8s}{'CV F1':>7s}{'CV Rec':>8s}|{'val PR':>8s}{'val ROC':>9s}"
          f"{'val F1':>8s}{'val Rec':>9s}{'composite':>11s}")
    for e in d["model_comparison"]["models"]:
        cv, v = e["cv"], {**e["validation"]["probability_metrics"], **e["validation"]["threshold_metrics"]}
        star = "*" if e["name"] == d["model_comparison"]["selected"] else " "
        print(f"{star}{e['name']:19s}{cv['pr_auc']['mean']:8.4f}{cv['roc_auc']['mean']:8.4f}{cv['f1']['mean']:7.3f}"
              f"{cv['recall']['mean']:8.3f}|{v['pr_auc']:8.4f}{v['roc_auc']:9.4f}{v['f1']:8.3f}{v['recall']:9.3f}"
              f"{e['composite']:11.4f}")
    print(f"Selected: {d['model_comparison']['selected']} - {d['model_comparison']['reason']}")
    print("\n== CALIBRATION (VALIDATION) ==")
    for m, c in d["calibration"]["candidates"].items():
        star = "*" if m == d["calibration"]["method"] else " "
        print(f"{star}{m:9s} brier={c['brier']:.4f} log_loss={c['log_loss']:.4f} ece={c['ece']:.4f} "
              f"roc_auc={c['roc_auc']:.4f} pr_auc={c['pr_auc']:.4f}")
    print(f"Selected: {d['calibration']['method']} - {d['calibration']['reason']}")
    t = d["threshold"]
    print(f"\n== THRESHOLD (VALIDATION, {t['metric']}) ==\nthreshold={t['threshold']:.3f} "
          f"precision={t['precision']:.4f} recall={t['recall']:.4f} f1={t['f1']:.4f}")
    f = d["final_test"]
    print("\n== FINAL TEST (evaluated once, after lock) ==")
    print("probability metrics :", {k: round(v, 4) for k, v in f["probability_metrics"].items()})
    tm = f["threshold_metrics"]
    print(f"threshold metrics @{f['selected_threshold']:.3f}:",
          {k: round(tm[k], 4) for k in ("accuracy", "precision", "recall", "f1")}, tm["confusion_matrix"])
    if rep.artifact:
        print(f"\nArtifact: {rep.artifact.model.relative_to(ROOT)}  sha256={rep.artifact.sha256[:12]}")
        print(f"Metadata: {rep.artifact.metadata.relative_to(ROOT)}")

    out = Path(args.out) if args.out else resolve_dir(opt["report"]["path"])
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(d, indent=2, default=str))
    print(f"\nFull report -> {out.relative_to(ROOT) if out.is_relative_to(ROOT) else out.name}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
