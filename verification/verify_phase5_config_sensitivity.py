from dataclasses import replace

import numpy as np
from sklearn.metrics import adjusted_rand_score

from ml.business import BusinessEngine, load_business_config
from ml.config import load_config
from ml.explainability import load_verified_artifact
from ml.pipelines.ingestion import DatasetSpec, load_csv
from ml.pipelines.training import split_raw
from ml.segmentation import load_segmentation_config, run_segmentation

spec = DatasetSpec.from_yaml("configs/datasets/telco.yaml")
tr = load_config("training")
ft = load_config("features")
cfg = load_segmentation_config()
biz = load_business_config()
ver = load_verified_artifact("models/trichurn_churn_model_v2.0.0.joblib")
train = split_raw(
    load_csv("ml/data/raw/telco_churn.csv"), spec, tr["split"]["val_size"], tr["split"]["test_size"], tr["seed"]
).train
probs = ver.artifact.predict_proba(train)
eng = BusinessEngine(biz, ver.artifact.threshold)
base = run_segmentation(train, probs, eng, spec, cfg, ft, tr)
print("base K", base.model.k, [p.segment_name for p in base.profiles])
# fixed K=4
k4 = run_segmentation(train, probs, eng, spec, cfg, ft, tr, k=4)
print("k=4 ->", k4.model.k, len(k4.profiles), "names unique:", len({p.segment_name for p in k4.profiles}) == 4)
# seed change (does not crash; ARI-equivalent)
s1 = run_segmentation(train, probs, eng, spec, replace(cfg, seed=1), ft, tr)
print(
    "seed=1 K",
    s1.model.k,
    "seed used",
    s1.seed,
    "ARI vs seed42 =",
    round(adjusted_rand_score(base.segment_ids, s1.segment_ids), 4),
)
# k_selection fixed
fx = replace(cfg, k_selection=replace(cfg.k_selection, method="fixed", fixed_k=5))
print("fixed_k=5 ->", run_segmentation(train, probs, eng, spec, fx, ft, tr).model.k)
# priority weights: all weight on avg_churn_probability changes ranking basis
w = replace(cfg.priority, weights={**{k: 0.0 for k in cfg.priority.weights}, "avg_churn_probability": 1.0})
pw = run_segmentation(train, probs, eng, spec, replace(cfg, priority=w), ft, tr)
print("base rank order", [p.segment_name for p in sorted(base.profiles, key=lambda p: p.priority_rank)])
print(
    "churn-only rank ",
    [p.segment_name for p in sorted(pw.profiles, key=lambda p: p.priority_rank)],
    "scores",
    [round(p.priority_score, 3) for p in pw.profiles],
)
# business config change: disable discount_offer -> strategies change, clustering does not
acts = {k: (replace(v, enabled=False) if k == "discount_offer" else v) for k, v in biz.actions.items()}
eng2 = BusinessEngine(replace(biz, actions=acts), ver.artifact.threshold)
nb = run_segmentation(train, probs, eng2, spec, cfg, ft, tr)
print(
    "discount disabled: clusters identical =",
    np.array_equal(base.segment_ids, nb.segment_ids),
    "| primary actions",
    {p.segment_name: p.strategy.primary_action_id for p in base.profiles},
    "->",
    {p.segment_name: p.strategy.primary_action_id for p in nb.profiles},
)
