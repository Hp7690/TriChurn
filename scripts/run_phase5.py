"""Phase 5 demo: segment TRAIN customers with K-Means and profile the segments with the Phase 4 business engine.

    python scripts/run_phase5.py [--k 4] [--no-save]

Flow: Telco CSV -> split (Phase 1.1) -> TRAIN customers -> locked Phase 2 model probabilities -> Phase 4 profiles;
independently, K-Means clusters the same customers from attributes only (no target, no probabilities). The TEST split
is never read; VALIDATION customers are only assigned to the fitted segments as an out-of-sample sanity check (no
labels or outcomes used). The Phase 2 churn artifact is verified before use and checked byte-identical afterwards.
"""
from __future__ import annotations

import argparse
import json
import sys
from collections import Counter
from dataclasses import asdict
from pathlib import Path

import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from ml.business import BusinessEngine, format_money, load_business_config  # noqa: E402
from ml.config import ROOT, load_config  # noqa: E402
from ml.errors import TriChurnError  # noqa: E402
from ml.explainability import load_verified_artifact  # noqa: E402
from ml.pipelines.ingestion import DatasetSpec, dataset_version, file_sha256, load_csv  # noqa: E402
from ml.pipelines.serialization import resolve_dir  # noqa: E402
from ml.pipelines.training import split_raw  # noqa: E402
from ml.segmentation import (  # noqa: E402
    assign_customers,
    build_metadata,
    fit_segmentation,
    load_segmentation_config,
    load_verified_segmentation_artifact,
    run_segmentation,
    save_segmentation_artifact,
)


def _rel(path: Path) -> str:
    try:
        return path.resolve().relative_to(ROOT).as_posix()
    except ValueError:
        return path.name


def main() -> int:
    # Legacy Windows code pages cannot encode every configured currency symbol.
    sys.stdout.reconfigure(errors="backslashreplace")
    ap = argparse.ArgumentParser()
    ap.add_argument("--model", default=str(ROOT / "models/trichurn_churn_model_v2.0.0.joblib"))
    ap.add_argument("--csv", default=str(ROOT / "ml/data/raw/telco_churn.csv"))
    ap.add_argument("--spec", default=str(ROOT / "configs/datasets/telco.yaml"))
    ap.add_argument("--k", type=int, default=None, help="override K (skips selection); default: configured selection")
    ap.add_argument("--no-save", action="store_true", help="do not write the segmentation artifact / report")
    ap.add_argument("--out-dir", default=None, help="write artifact + report here instead of the configured paths")
    args = ap.parse_args()
    churn_path = Path(args.model)
    churn_sha_before = file_sha256(churn_path) if churn_path.exists() else None
    try:
        spec, training, features = DatasetSpec.from_yaml(args.spec), load_config("training"), load_config("features")
        cfg, business = load_segmentation_config(), load_business_config()
        verified = load_verified_artifact(churn_path)
        df = load_csv(args.csv)
        sp = training["split"]
        parts = split_raw(df, spec, sp["val_size"], sp["test_size"], training["seed"])
        train = parts.train
        probs = verified.artifact.predict_proba(train)
        engine = BusinessEngine(business, verified.artifact.threshold)
        res = run_segmentation(train, probs, engine, spec, cfg, features, training, args.k)
        again, _ = fit_segmentation(train, spec, cfg, features, res.seed, res.model.k)
        reproducible = bool(np.array_equal(res.segment_ids, again.assign(train)[0]))
        names = {p.segment_id: p.segment_name for p in res.profiles}
        val_assign = assign_customers(res.model, names, parts.val, spec.id_column)
    except TriChurnError as exc:
        print(f"ERROR: {exc}")
        return 1

    cur = business.currency
    sel = res.selection
    print(f"Customers segmented: {len(train)} (TRAIN split; TEST never read)   seed={res.seed}   K={res.model.k}")
    print(f"Clustering features: {list(res.model.feature_names)}  (no target, no churn probability, no Phase 4 output)")
    if sel:
        print("\nK selection (silhouette; eligible = K in business range and smallest cluster large enough):")
        for c in sel.candidates:
            mark = "*" if c.k == sel.selected_k else " "
            why = "" if c.eligible else f"   [not eligible: {c.ineligible_reason}]"
            print(f" {mark} K={c.k} silhouette={c.silhouette:.4f} min_cluster={c.min_cluster_share:.1%} "
                  f"inertia={c.extra['inertia']:.0f} CH={c.extra['calinski_harabasz']:.0f} "
                  f"DB={c.extra['davies_bouldin']:.3f}{why}")
        print(f"   {sel.rationale}")
    print("\nSegments (ordered by priority; business columns come from Phase 4 profiles):")
    for p in sorted(res.profiles, key=lambda q: q.priority_rank):
        print(f"\n#{p.priority_rank} [{p.priority_tier}] segment {p.segment_id}: {p.segment_name}  "
              f"(priority score {p.priority_score:.3f})")
        print(f"   customers {p.customer_count} ({p.customer_pct:.1%})   tenure {p.avg_tenure:.1f}m   "
              f"monthly {p.avg_monthly_charges:.2f}   total {p.avg_total_charges:.2f}")
        print(f"   avg churn prob {p.avg_churn_probability:.3f} ({p.risk_band})   "
              f"avg CLV {format_money(p.avg_clv, cur)}   total CLV {format_money(p.total_clv, cur)}")
        print(f"   total value at risk {format_money(p.total_value_at_risk, cur)}   avg ENB "
              f"{format_money(p.avg_enb, cur)}   intervention rate {p.intervention_rate:.1%}")
        print(f"   strategy: {p.strategy.summary}")
    print("\nValidation customers assigned to TRAIN-fitted segments (shares; no outcomes used):")
    vc = Counter(a.segment_id for a in val_assign)
    print("   " + "  ".join(f"{names[s]}: {vc.get(s, 0) / len(val_assign):.1%}" for s in sorted(names)))
    print(f"\nReproducible (refit with same seed gives identical assignments): {reproducible}")
    if not reproducible:
        print("ERROR: segmentation is not reproducible.")
        return 1

    if not args.no_save:
        dataset = {"path": _rel(Path(args.csv)), "version": dataset_version(args.csv), "rows": len(df)}
        sizes = {"train": len(parts.train), "validation": len(parts.val), "test": len(parts.test)}
        meta = build_metadata(res.model, cfg, res.seed, res.selection, res.profiles, dataset_info=dataset,
                              split_sizes=sizes, n_train_customers=len(train), business_config=asdict(business),
                              churn_model_sha256=verified.sha256)
        artifact_dir = args.out_dir or cfg.artifact_dir
        paths = save_segmentation_artifact(res.model, meta, artifact_dir, cfg.artifact_name)
        reloaded = load_verified_segmentation_artifact(paths.model)
        assert np.array_equal(reloaded.model.assign(train)[0], res.segment_ids), "reloaded artifact disagrees"
        report = {
            "phase": "5 - customer segmentation and segment intelligence", "dataset": dataset, "split_sizes": sizes,
            "split_used": "TRAIN (TEST never read)", "seed": res.seed, "selected_k": res.model.k,
            "model_threshold": verified.artifact.threshold, "churn_model_sha256": verified.sha256,
            "k_selection": None if sel is None else sel.to_dict(),
            "segments": [p.to_dict() for p in sorted(res.profiles, key=lambda q: q.priority_rank)],
            "validation_assignment_shares": {names[s]: vc.get(s, 0) / len(val_assign) for s in sorted(names)},
            "reproducible": reproducible,
            "artifact": {"model": _rel(paths.model), "metadata": _rel(paths.metadata), "sha256": paths.sha256},
            "note": "Segments are descriptive; business figures are estimates under assumptions, not causal."}
        out = Path(args.out_dir) / Path(cfg.report_path).name if args.out_dir else resolve_dir(".") / cfg.report_path
        out.parent.mkdir(parents=True, exist_ok=True)
        out.write_text(json.dumps(report, indent=2, default=str))
        print(f"\nArtifact: {_rel(paths.model)}  sha256={paths.sha256[:12]}\nMetadata: {_rel(paths.metadata)}"
              f"\nReport:   {_rel(out)}")
    if churn_sha_before is not None:
        unchanged = file_sha256(churn_path) == churn_sha_before
        print(f"Phase 2 churn artifact unchanged: {unchanged}")
        if not unchanged:
            return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
