import json
import shutil
from pathlib import Path

import numpy as np

from ml.business import BusinessEngine, load_business_config
from ml.config import load_config
from ml.errors import ArtifactIntegrityError
from ml.explainability import load_verified_artifact
from ml.pipelines.ingestion import DatasetSpec, load_csv
from ml.pipelines.training import split_raw
from ml.segmentation import (
    fit_segmentation,
    load_segmentation_config,
    load_verified_segmentation_artifact,
    run_segmentation,
)

R = Path(".")
spec = DatasetSpec.from_yaml("configs/datasets/telco.yaml")
tr = load_config("training")
ft = load_config("features")
cfg = load_segmentation_config()
biz = load_business_config()
ver = load_verified_artifact("models/trichurn_churn_model_v2.0.0.joblib")
parts = split_raw(
    load_csv("ml/data/raw/telco_churn.csv"), spec, tr["split"]["val_size"], tr["split"]["test_size"], tr["seed"]
)
train = parts.train
probs = ver.artifact.predict_proba(train)
eng = BusinessEngine(biz, ver.artifact.threshold)
res = run_segmentation(train, probs, eng, spec, cfg, ft, tr)
print("N train", len(train), "K", res.model.k, "split sizes", len(parts.train), len(parts.val), len(parts.test))

# 1. shipped artifact vs fresh fit (verified load)
for label, p in [
    ("shipped", "models/trichurn_segmentation_v5.0.0.joblib"),
    ("fresh", "/tmp/s5a/trichurn_segmentation_v5.0.0.joblib"),
]:
    v = load_verified_segmentation_artifact(p)
    same = np.array_equal(v.model.assign(train)[0], res.segment_ids)
    cent = np.allclose(v.model.centers, res.model.centers, atol=1e-9)
    print(
        f"[{label}] verified-load OK sha={v.sha256[:12]} assignments_equal={same} centroids_equal={cent} "
        f"uses_target={v.metadata['training']['uses_target']} uses_test={v.metadata['training']['uses_test']} "
        f"churn_sha_recorded={v.metadata['profiling_provenance']['churn_model_sha256'][:12]}"
    )
a = json.load(open("/tmp/s5a/phase5_report.json"))
b = json.load(open("/tmp/s5b/phase5_report.json"))
for d in (a, b):
    d["artifact"].pop("sha256")
print("reports identical apart from artifact sha:", a == b)

# 2. tamper detection
t = Path("/tmp/tamper")
shutil.rmtree(t, ignore_errors=True)
t.mkdir()
for f in ("joblib", "metadata.json"):
    shutil.copy(f"/tmp/s5a/trichurn_segmentation_v5.0.0.{f}", t)
raw = bytearray((t / "trichurn_segmentation_v5.0.0.joblib").read_bytes())
raw[len(raw) // 2] ^= 0xFF
(t / "trichurn_segmentation_v5.0.0.joblib").write_bytes(bytes(raw))
try:
    load_verified_segmentation_artifact(t / "trichurn_segmentation_v5.0.0.joblib")
    print("TAMPER NOT DETECTED")
except ArtifactIntegrityError as e:
    print("tamper detected:", str(e)[:90])
m = json.load(open(t / "trichurn_segmentation_v5.0.0.metadata.json"))
m["artifact_sha256"] = "0" * 64
shutil.copy("/tmp/s5a/trichurn_segmentation_v5.0.0.joblib", t)
json.dump(m, open(t / "trichurn_segmentation_v5.0.0.metadata.json", "w"))
try:
    load_verified_segmentation_artifact(t / "trichurn_segmentation_v5.0.0.joblib")
    print("BAD SIDECAR NOT DETECTED")
except ArtifactIntegrityError as e:
    print("bad sidecar detected:", str(e)[:60])

# 3. leakage isolation: scramble labels + random probabilities -> clustering identical
rng = np.random.default_rng(7)
scr = train.copy()
scr[spec.target] = rng.permutation(scr[spec.target].values)
noise = rng.uniform(0, 1, len(scr))
res2 = run_segmentation(scr, noise, eng, spec, cfg, ft, tr)
print(
    "scrambled labels+noise probs: assignments identical =",
    np.array_equal(res.segment_ids, res2.segment_ids),
    "centroids identical =",
    np.array_equal(res.model.centers, res2.model.centers),
    "| profile numbers changed =",
    res.profiles[0].avg_churn_probability != res2.profiles[0].avg_churn_probability,
)
no_target = train.drop(columns=[spec.target])
m3, _ = fit_segmentation(no_target, spec, cfg, ft, res.seed, res.model.k)
print(
    "fit without target column present: assignments identical =",
    np.array_equal(m3.assign(no_target)[0], res.segment_ids),
)
# test split influence: fit on train never sees test; assert train-fit independent of test frame
print("feature list:", res.model.feature_names)

# 4. independent recompute of segment aggregates from raw Phase 4 profiles
bp = res.business_profiles
ids = res.segment_ids
ok = True
for p in res.profiles:
    idx = np.where(ids == p.segment_id)[0]
    sub = [bp[i] for i in idx]
    checks = {
        "count": len(sub) == p.customer_count,
        "avg_p": np.isclose(np.mean([s.churn_probability for s in sub]), p.avg_churn_probability),
        "avg_clv": np.isclose(np.mean([s.clv for s in sub]), p.avg_clv),
        "var": np.isclose(sum(s.value_at_risk for s in sub), p.total_value_at_risk),
        "enb": np.isclose(sum(s.expected_net_benefit for s in sub), p.total_enb),
        "int": sum(s.intervention_decision == "INTERVENE" for s in sub) == p.intervention_count,
        "tenure": np.isclose(train.iloc[idx]["tenure"].mean(), p.avg_tenure),
    }
    ok &= all(checks.values())
    print(p.segment_id, p.segment_name, {k: v for k, v in checks.items() if not v} or "all aggregates match")
shares = sum(p.customer_pct for p in res.profiles)
print("pct sum", round(shares, 6), "ok", ok)
sc = [p.priority_score for p in res.profiles]
print("priority scores in [0,1]:", all(0 <= s <= 1 for s in sc))
