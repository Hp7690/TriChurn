"""Phase 1 CLI: validate, profile and train the three baseline models on a CSV.

    python scripts/run_phase1.py [--csv PATH] [--spec configs/datasets/telco.yaml]
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
from ml.pipelines.training import run_training  # noqa: E402

ROOT = Path(__file__).resolve().parents[1]


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--csv", default=str(ROOT / "ml/data/raw/telco_churn.csv"))
    ap.add_argument("--spec", default=str(ROOT / "configs/datasets/telco.yaml"))
    ap.add_argument("--out", default=str(ROOT / "ml/experiments/phase1_report.json"))
    args = ap.parse_args()
    warnings.filterwarnings("ignore")

    quality, training, features = (load_config(n) for n in ("quality", "training", "features"))
    try:
        df = load_csv(args.csv, quality["limits"]["max_file_mb"])
        rep = run_training(df, DatasetSpec.from_yaml(args.spec), quality, training, features,
                           dataset_info={"path": args.csv, "version": dataset_version(args.csv)})
    except TriChurnError as exc:
        print(f"ERROR: {exc}")
        return 1

    d = rep.to_dict()
    q = d["quality"]
    print(f"Dataset {d['dataset'].get('version')}  rows={d['profile']['rows']}  "
          f"quality={q['score']} ({q['band']})  components={q['components']}")
    print(f"Dataset warnings (raw):   {[w['code'] + ':' + str(w['column']) for w in d['validation']['warnings']]}")
    print(f"Training warnings (train): "
          f"{[w['code'] + ':' + str(w['column']) for w in d['training_validation']['warnings']]}")
    print(f"Engineered: {d['engineered_features']['created']}")
    print(f"Skipped:    {d['engineered_features']['skipped']}")
    print(f"Splits: {d['split_sizes']}\n")
    hdr = (f"{'model':20s}{'imbal':9s}{'sel':4s}{'CV PR-AUC':>16s}{'CV ROC-AUC':>16s}"
           f"{'val ROC':>9s}{'val PR':>8s}{'val Rec':>9s}{'val F1':>8s}")
    print(hdr)
    for r in d["results"]:
        cv, v = r["cv"], r["validation"]
        print(f"{r['name']:20s}{r['imbalance']:9s}{'*' if r['selected_imbalance'] else '':4s}"
              f"{cv['pr_auc']['mean']:>9.3f}±{cv['pr_auc']['std']:.3f}"
              f"{cv['roc_auc']['mean']:>9.3f}±{cv['roc_auc']['std']:.3f}"
              f"{v['roc_auc']:>9.3f}{v['pr_auc']:>8.3f}{v['recall']:>9.3f}{v['f1']:>8.3f}")
    Path(args.out).parent.mkdir(parents=True, exist_ok=True)
    Path(args.out).write_text(json.dumps(d, indent=2))
    print(f"\nFull report -> {args.out}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
