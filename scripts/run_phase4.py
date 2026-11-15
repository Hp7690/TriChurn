"""Phase 4 demo: score TRAIN-split customers with the locked model and show business decisions.

    python scripts/run_phase4.py [--n 500]

Uses the TRAIN split only (the TEST split is never read) and changes nothing on disk except an optional JSON summary.
This is an illustration of the decision pipeline, not an evaluation: CLV and success rates are configured assumptions.
"""
from __future__ import annotations

import argparse
import json
import sys
from collections import Counter
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from ml.business import BusinessEngine, format_profile, load_business_config  # noqa: E402
from ml.config import load_config  # noqa: E402
from ml.errors import TriChurnError  # noqa: E402
from ml.explainability import ChurnShapExplainer, load_train_background, load_verified_artifact  # noqa: E402
from ml.pipelines.ingestion import DatasetSpec, load_csv  # noqa: E402
from ml.pipelines.training import split_raw  # noqa: E402

ROOT = Path(__file__).resolve().parents[1]


def main() -> int:
    if hasattr(sys.stdout, 'reconfigure'):
        sys.stdout.reconfigure(encoding='utf-8', errors='backslashreplace')
    ap = argparse.ArgumentParser()
    ap.add_argument("--model", default=str(ROOT / "models/trichurn_churn_model_v2.0.0.joblib"))
    ap.add_argument("--csv", default=str(ROOT / "ml/data/raw/telco_churn.csv"))
    ap.add_argument("--spec", default=str(ROOT / "configs/datasets/telco.yaml"))
    ap.add_argument("--n", type=int, default=500, help="number of TRAIN customers to score")
    ap.add_argument("--out", default=None, help="optional JSON file for the portfolio summary")
    args = ap.parse_args()
    try:
        spec, training = DatasetSpec.from_yaml(args.spec), load_config("training")
        verified = load_verified_artifact(args.model)
        parts = split_raw(load_csv(args.csv), spec, training["split"]["val_size"], training["split"]["test_size"],
                          training["seed"])
        customers = parts.train.head(args.n)
        cfg = load_business_config()
        engine = BusinessEngine(cfg, verified.artifact.threshold)
        profiles = engine.profile_frame(customers, verified.artifact.predict_proba(customers), spec.id_column)
        explainer = ChurnShapExplainer(verified, load_train_background(args.csv, spec, verified))
    except TriChurnError as exc:
        print(f"ERROR: {exc}")
        return 1

    cur = cfg.currency.code
    treated = [p for p in profiles if p.intervention_decision == "INTERVENE"]
    summary = {
        "customers_scored": len(profiles), "split": "TRAIN (not an evaluation; TEST never read)",
        "model_threshold": verified.artifact.threshold, "currency": cur,
        "decisions": dict(Counter(p.intervention_decision for p in profiles)),
        "risk_bands": dict(Counter(p.risk_band for p in profiles)),
        "recommended_actions": dict(Counter(p.recommended_action_id for p in treated)),
        "total_value_at_risk": sum(p.value_at_risk for p in profiles),
        "total_estimated_expected_net_benefit_of_recommended_actions": sum(p.expected_net_benefit for p in treated),
        "note": "Estimates under configured assumptions; not causal effects.",
    }
    print(json.dumps(summary, indent=2))
    top = max(treated, key=lambda p: p.expected_net_benefit)
    print("\n--- Highest expected-net-benefit customer ---\n" + format_profile(top, cfg.currency))
    row = customers[customers[spec.id_column] == top.customer_id]
    ex = engine.explain(top, explainer.explain(row)).to_dict()
    print("\nMODEL EXPLANATION:\n  " + ex["MODEL EXPLANATION"])
    print("\nBUSINESS DECISION:\n  " + ex["BUSINESS DECISION"])
    print("\n" + ex["disclaimer"])
    if args.out:
        Path(args.out).write_text(json.dumps(summary, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
