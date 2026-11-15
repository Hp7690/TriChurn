"""Phase 5 - segmentation artifact (serialization, integrity, reproducibility) and architecture guards."""
import ast
import hashlib
import json
from dataclasses import asdict
from pathlib import Path

import joblib
import numpy as np
import pytest

from ml.business import BusinessEngine, load_business_config
from ml.config import ROOT
from ml.errors import ArtifactIntegrityError
from ml.segmentation import (
    assign_customers,
    build_metadata,
    clusterings_equivalent,
    fit_segmentation,
    load_segmentation_config,
    load_verified_segmentation_artifact,
    run_segmentation,
    save_segmentation_artifact,
)
from tests.conftest import make_segment_frame

SEG_DIR = ROOT / "ml" / "segmentation"


@pytest.fixture(scope="module")
def built(spec, features_cfg, training_cfg):
    frame = make_segment_frame(n_per_group=60, seed=8)
    cfg, business = load_segmentation_config(), load_business_config()
    probs = frame["group"].map({0: 0.8, 1: 0.4, 2: 0.1}).to_numpy()
    res = run_segmentation(frame, probs, BusinessEngine(business, 0.34), spec, cfg, features_cfg, training_cfg)
    meta = build_metadata(res.model, cfg, res.seed, res.selection, res.profiles,
                          dataset_info={"path": "ml/data/raw/x.csv", "version": "sha256:abc", "rows": len(frame)},
                          split_sizes={"train": len(frame)}, n_train_customers=len(frame),
                          business_config=asdict(business), churn_model_sha256="f" * 64,
                          trained_at="2026-01-01T00:00:00+00:00")
    return frame, cfg, res, meta


@pytest.fixture()
def saved(built, tmp_path):
    frame, cfg, res, meta = built
    return save_segmentation_artifact(res.model, meta, tmp_path, cfg.artifact_name), built


def test_roundtrip_gives_identical_assignments_and_names(saved):
    paths, (frame, cfg, res, meta) = saved
    loaded = load_verified_segmentation_artifact(paths.model)
    ids, dist = loaded.model.assign(frame)
    assert np.array_equal(ids, res.segment_ids) and np.allclose(dist, res.model.assign(frame)[1])
    assert np.array_equal(loaded.model.centers, res.model.centers)
    assert loaded.segment_names == {p.segment_id: p.segment_name for p in res.profiles}
    assert loaded.sha256 == paths.sha256 == hashlib.sha256(paths.model.read_bytes()).hexdigest()
    out = assign_customers(loaded.model, loaded.segment_names, frame, "customerID")
    assert [a.segment_name for a in out] == [a.segment_name for a in res.assignments]


def test_metadata_documents_what_was_used_and_what_was_not(saved):
    paths, (frame, cfg, res, _) = saved
    side = json.loads(paths.metadata.read_text())
    assert side["kind"] == "segmentation" and side["model_version"] == "5.0.0" and side["random_state"] == 42
    assert side["selected_k"] == 3 and side["feature_names"] == list(cfg.features.all)
    assert side["feature_count"] == 5 and side["k_selection"]["selected_k"] == 3
    assert side["preprocessing"] == {"imputation": "median", "scaling": "standard",
                                     "steps": ["features", "impute", "scale"]}
    assert side["kmeans"]["init"] == "k-means++" and side["kmeans"]["n_init"] == 10
    assert side["training"]["fit_split"] == "train" and side["training"]["n_customers"] == len(frame)
    assert not any(side["training"][k] for k in ("uses_target", "uses_churn_probability", "uses_validation",
                                                  "uses_test"))
    assert "dataset target" in side["excluded_from_clustering"]["always"]
    assert "churn_probability" in side["excluded_from_clustering"]["always"]
    assert side["dataset"]["version"] == "sha256:abc" and side["dataset"]["split_sizes"] == {"train": len(frame)}
    assert len(side["profiling_provenance"]["business_config_sha256"]) == 64
    assert side["profiling_provenance"]["churn_model_sha256"] == "f" * 64
    assert side["artifact_sha256"] == paths.sha256 and side["artifact_file"] == paths.model.name
    assert [c["segment_id"] for c in side["segment_catalog"]] == [0, 1, 2]
    assert len(side["centroids_original_units"]) == 3 and set(side["centroids_original_units"][0]) == set(
        cfg.features.all)
    text = paths.metadata.read_text()
    assert str(paths.model.parent) not in text and str(ROOT) not in text           # no machine-specific paths


def test_tampered_artifact_bytes_are_rejected_before_deserialisation(saved):
    paths, _ = saved
    raw = bytearray(paths.model.read_bytes())
    raw[len(raw) // 2] ^= 0xFF
    paths.model.write_bytes(bytes(raw))
    with pytest.raises(ArtifactIntegrityError, match="SHA-256 mismatch"):
        load_verified_segmentation_artifact(paths.model)


def test_tampered_or_missing_sidecar_digest_is_rejected(saved):
    paths, _ = saved
    side = json.loads(paths.metadata.read_text())
    paths.metadata.write_text(json.dumps({**side, "artifact_sha256": "0" * 64}))
    with pytest.raises(ArtifactIntegrityError, match="SHA-256 mismatch"):
        load_verified_segmentation_artifact(paths.model)
    paths.metadata.write_text(json.dumps({k: v for k, v in side.items() if k != "artifact_sha256"}))
    with pytest.raises(ArtifactIntegrityError, match="No valid SHA-256"):
        load_verified_segmentation_artifact(paths.model)
    assert load_verified_segmentation_artifact(paths.model, expected_sha256=paths.sha256).sha256 == paths.sha256
    with pytest.raises(ArtifactIntegrityError, match="mismatch"):
        load_verified_segmentation_artifact(paths.model, expected_sha256="1" * 64)
    paths.metadata.unlink()
    with pytest.raises(ArtifactIntegrityError, match="Cannot read"):
        load_verified_segmentation_artifact(paths.model)


def test_sidecar_that_disagrees_with_the_embedded_metadata_is_rejected(saved):
    paths, _ = saved
    side = json.loads(paths.metadata.read_text())
    paths.metadata.write_text(json.dumps({**side, "selected_k": 5}))
    with pytest.raises(ArtifactIntegrityError, match="disagree on selected_k"):
        load_verified_segmentation_artifact(paths.model)


def test_a_non_segmentation_bundle_is_refused_even_with_a_valid_hash(tmp_path):
    path = tmp_path / "other_v1.joblib"
    joblib.dump({"schema_version": 1, "model": object(), "threshold": 0.3, "metadata": {}}, path)
    digest = hashlib.sha256(path.read_bytes()).hexdigest()
    (tmp_path / "other_v1.metadata.json").write_text(json.dumps({"artifact_sha256": digest}))
    with pytest.raises(ArtifactIntegrityError, match="not a Phase 5 segmentation artifact"):
        load_verified_segmentation_artifact(path)


def test_saving_never_touches_the_phase2_churn_artifact(built, tmp_path):
    _, cfg, res, meta = built
    churn = ROOT / "models" / "trichurn_churn_model_v2.0.0.joblib"
    before = hashlib.sha256(churn.read_bytes()).hexdigest() if churn.exists() else None
    paths = save_segmentation_artifact(res.model, meta, tmp_path, cfg.artifact_name)
    assert paths.model.name == "trichurn_segmentation_v5.0.0.joblib" != churn.name
    assert paths.metadata.name == "trichurn_segmentation_v5.0.0.metadata.json"
    assert (hashlib.sha256(churn.read_bytes()).hexdigest() if churn.exists() else None) == before
    assert not list(tmp_path.glob("trichurn_churn*"))


def test_artifact_is_reproducible_across_independent_fits(built, spec, features_cfg, tmp_path):
    frame, cfg, res, meta = built
    again, selection = fit_segmentation(frame, spec, cfg, features_cfg, 42)
    assert np.array_equal(again.centers, res.model.centers)
    p1 = save_segmentation_artifact(res.model, meta, tmp_path / "a", cfg.artifact_name)
    meta2 = {**meta, "k_selection": selection.to_dict()}
    p2 = save_segmentation_artifact(again, meta2, tmp_path / "b", cfg.artifact_name)
    a, b = (load_verified_segmentation_artifact(p.model) for p in (p1, p2))
    assert np.array_equal(a.model.centers, b.model.centers)
    assert clusterings_equivalent(a.model.assign(frame)[0], b.model.assign(frame)[0])
    assert a.metadata["centroids_original_units"] == b.metadata["centroids_original_units"]


# ------------------------------------------------------------------------------------------- architecture
def _imports(path: Path) -> set[str]:
    mods = set()
    for node in ast.walk(ast.parse(path.read_text())):
        if isinstance(node, ast.Import):
            mods.update(a.name for a in node.names)
        elif isinstance(node, ast.ImportFrom) and node.module:
            mods.add(node.module)
    return mods


def test_segmentation_package_has_no_web_db_or_infrastructure_dependencies():
    banned = {"fastapi", "starlette", "uvicorn", "sqlalchemy", "psycopg2", "flask", "django", "streamlit",
              "mlflow", "dvc", "airflow", "requests", "httpx", "shap", "backend", "frontend"}
    for f in SEG_DIR.glob("*.py"):
        assert not {m.split(".")[0] for m in _imports(f)} & banned, f.name


def test_clustering_modules_cannot_see_business_outputs_or_the_churn_model():
    """features/clustering/config/schemas are unsupervised: no Phase 4, SHAP, tuning or model-artifact imports."""
    for name in ("features.py", "clustering.py", "config.py", "schemas.py"):
        mods = _imports(SEG_DIR / name)
        assert not [m for m in mods if m.startswith(("ml.business", "ml.explainability", "ml.segmentation.profiling",
                                                      "ml.segmentation.engine", "ml.segmentation.artifact"))], name
        assert not [m for m in mods if m in ("ml.pipelines.serialization", "ml.pipelines.optimization",
                                             "ml.pipelines.training", "ml.pipelines.final_evaluation")], name


def test_phase5_reuses_phase4_instead_of_reimplementing_it():
    src = " ".join((SEG_DIR / f).read_text() for f in ("profiling.py", "engine.py", "clustering.py", "features.py"))
    for token in ("gross_margin", "discounted_months", "lifetime_months", "success_rate", "expected_cost",
                  "revenue_multiplier", "compute_enb", "compute_clv", "select_best_action", "decide("):
        assert token not in src, token
    for f in SEG_DIR.glob("*.py"):
        mods = _imports(f)
        assert not [m for m in mods if m.startswith(("ml.business.clv", "ml.business.enb", "ml.business.decision",
                                                      "ml.business.retention", "ml.business.what_if"))], f.name


def test_phase4_and_earlier_packages_do_not_depend_on_phase5():
    for pkg in ("business", "pipelines", "explainability"):
        for f in (ROOT / "ml" / pkg).glob("*.py"):
            assert not [m for m in _imports(f) if m.startswith("ml.segmentation")], f
    assert not [m for m in _imports(ROOT / "ml" / "config.py") if m.startswith("ml.segmentation")]


def test_segmentation_logic_is_deterministic_and_seeded_explicitly():
    for f in ("profiling.py", "engine.py", "features.py"):
        src = (SEG_DIR / f).read_text()
        assert "np.random" not in src and "default_rng" not in src and "import random" not in src, f
    assert "random_state=seed" in (SEG_DIR / "clustering.py").read_text()
