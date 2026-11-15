"""Phase 3 - SHAP explainability tests. A small LR artifact is built on synthetic data (tests only); the real
locked artifact is exercised in the integration section at the bottom (skipped when files are missing)."""
from __future__ import annotations

import copy
import hashlib
import json
import math
from pathlib import Path

import joblib
import numpy as np
import pandas as pd
import pytest
from scipy.special import expit

import ml.explainability.shap_explainer as se
from ml.config import deep_merge, load_config
from ml.errors import ArtifactIntegrityError, ExplainabilityError, ExplainabilityInputError
from ml.explainability import (
    ChurnShapExplainer,
    FeatureMap,
    build_feature_map,
    global_importance,
    load_train_background,
    load_verified_artifact,
    select_background,
    top_negative_drivers,
    top_positive_drivers,
    validate_input,
)
from ml.explainability.schemas import DIRECTIONS, FeatureContribution, LocalExplanation
from ml.pipelines.calibration import CalibratedModel, IdentityCalibrator, SigmoidCalibrator
from ml.pipelines.ingestion import dataset_version
from ml.pipelines.preprocessing import build_pipeline, build_preprocessor, plan_features, prepare_xy
from ml.pipelines.training import make_estimator, split_raw
from tests.conftest import make_churn_frame

SEED = 42


# ------------------------------------------------------------------------------------------- helpers
def _write_artifact(directory: Path, bundle: dict, meta: dict, name: str = "m_v1") -> Path:
    directory.mkdir(parents=True, exist_ok=True)
    model_path = directory / f"{name}.joblib"
    joblib.dump(bundle, model_path, compress=3)
    digest = hashlib.sha256(model_path.read_bytes()).hexdigest()
    (directory / f"{name}.metadata.json").write_text(
        json.dumps({**meta, "artifact_file": model_path.name, "artifact_sha256": digest}, indent=2, default=str))
    return model_path


@pytest.fixture(scope="module")
def world(tmp_path_factory, spec, quality_cfg, training_cfg, features_cfg):
    root = tmp_path_factory.mktemp("phase3")
    df = make_churn_frame(n=1200, seed=1)
    csv = root / "churn.csv"
    df.to_csv(csv, index=False)
    parts = split_raw(df, spec, 0.15, 0.15, SEED)
    plan = plan_features(parts.train, spec, quality_cfg)
    X_train, y_train, _ = prepare_xy(parts.train, spec, plan)
    pipe = build_pipeline(plan, make_estimator("logistic_regression", "none", y_train, training_cfg, SEED),
                          features_cfg).fit(X_train, y_train)
    model = CalibratedModel(pipe, IdentityCalibrator(), "none")
    meta = {
        "model_name": "logistic_regression", "model_version": "t", "feature_names": list(plan.features),
        "model_feature_names": [str(n) for n in pipe.named_steps["preprocess"].get_feature_names_out()],
        "target": spec.target, "calibration": {"method": "none", "parameters": {"method": "none"}},
        "threshold": {"value": 0.34, "metric": "f1", "source": "optimized"}, "random_state": SEED,
        "training_configuration": {"training": training_cfg},
        "dataset": {"version": dataset_version(csv),
                    "split_sizes": {"train": len(parts.train), "validation": len(parts.val),
                                    "test": len(parts.test)}},
    }
    bundle = {"schema_version": 1, "model": model, "threshold": 0.34, "metadata": meta}
    path = _write_artifact(root / "ok", bundle, meta)
    return {"root": root, "df": df, "csv": csv, "parts": parts, "plan": plan, "pipe": pipe, "model": model,
            "meta": meta, "bundle": bundle, "path": path, "spec": spec}


@pytest.fixture(scope="module")
def verified(world):
    return load_verified_artifact(world["path"])


@pytest.fixture(scope="module")
def background(world, verified):
    return load_train_background(world["csv"], world["spec"], verified)


@pytest.fixture(scope="module")
def explainer(verified, background):
    return ChurnShapExplainer(verified, background)


@pytest.fixture(scope="module")
def records(world):
    """Raw customer records from the VALIDATION split (any rows would do; never used as background)."""
    return world["parts"].val[world["plan"].features].head(40).reset_index(drop=True)


def _cfg(**over):
    return deep_merge(load_config("explainability"), over)


# ====================================================================================== artifact / SHA-256
def test_valid_artifact_loads_and_hash_matches(world, verified):
    side = json.loads(world["path"].with_name("m_v1.metadata.json").read_text())
    assert verified.sha256 == side["artifact_sha256"] == hashlib.sha256(world["path"].read_bytes()).hexdigest()
    assert verified.artifact.threshold == 0.34


def test_tampered_artifact_is_rejected_and_never_deserialised(world, tmp_path, monkeypatch):
    d = tmp_path / "t"
    d.mkdir()
    for suffix in (".joblib", ".metadata.json"):
        (d / f"m_v1{suffix}").write_bytes(world["path"].with_name(f"m_v1{suffix}").read_bytes())
    with open(d / "m_v1.joblib", "ab") as fh:
        fh.write(b"\x00tampered")
    called = []
    monkeypatch.setattr(se.joblib, "load", lambda *a, **k: called.append(1))
    with pytest.raises(ArtifactIntegrityError, match="SHA-256 mismatch"):
        load_verified_artifact(d / "m_v1.joblib")
    assert not called, "a tampered file must be rejected BEFORE deserialisation"


def test_expected_sha256_override_and_missing_digest(world, tmp_path):
    with pytest.raises(ArtifactIntegrityError, match="mismatch"):
        load_verified_artifact(world["path"], expected_sha256="0" * 64)
    side = json.loads(world["path"].with_name("m_v1.metadata.json").read_text())
    side.pop("artifact_sha256")
    (tmp_path / "m_v1.joblib").write_bytes(world["path"].read_bytes())
    (tmp_path / "m_v1.metadata.json").write_text(json.dumps(side))
    with pytest.raises(ArtifactIntegrityError, match="No valid SHA-256"):
        load_verified_artifact(tmp_path / "m_v1.joblib")


def test_metadata_mismatch_is_rejected(world, tmp_path):
    # (a) valid hash but the embedded threshold contradicts the trusted sidecar
    bundle = copy.deepcopy({k: v for k, v in world["bundle"].items() if k != "model"})
    bundle["model"] = world["model"]
    bundle["threshold"] = 0.5
    p = _write_artifact(tmp_path / "a", bundle, world["meta"])
    with pytest.raises(ArtifactIntegrityError, match="disagree on threshold"):
        load_verified_artifact(p)
    # (b) sidecar describes a different file
    p2 = _write_artifact(tmp_path / "b", world["bundle"], world["meta"])
    side_path = p2.with_name("m_v1.metadata.json")
    side = json.loads(side_path.read_text())
    side["artifact_file"] = "other.joblib"
    side_path.write_text(json.dumps(side))
    with pytest.raises(ArtifactIntegrityError, match="not 'm_v1.joblib'"):
        load_verified_artifact(p2)
    # (c) missing sidecar
    (tmp_path / "c").mkdir()
    (tmp_path / "c" / "m_v1.joblib").write_bytes(world["path"].read_bytes())
    with pytest.raises(ArtifactIntegrityError, match="Cannot read trusted metadata"):
        load_verified_artifact(tmp_path / "c" / "m_v1.joblib")


# ================================================================================================ explainer
def test_explainer_uses_linear_explainer_on_the_locked_model(explainer, world):
    assert "LinearExplainer" in explainer.explainer_type
    assert explainer.output_space == "log_odds"
    lr = explainer.base_pipeline.named_steps["model"]               # the stored model, not a retrained one
    assert type(lr).__name__ == "LogisticRegression"
    np.testing.assert_array_equal(lr.coef_, world["pipe"].named_steps["model"].coef_)
    assert explainer.threshold == 0.34
    d = explainer.describe()
    assert d["background_source"].startswith("TRAIN") and d["n_source_features"] > 0


def test_calibrated_model_is_refused(world, tmp_path):
    p = world["model"].base.predict_proba(world["parts"].train[world["plan"].features])[:, 1]
    y = np.random.default_rng(0).integers(0, 2, len(p))
    cal = CalibratedModel(world["pipe"], SigmoidCalibrator().fit(p, y), "sigmoid")
    meta = {**world["meta"], "calibration": {"method": "sigmoid", "parameters": {}}}
    bundle = {"schema_version": 1, "model": cal, "threshold": 0.34, "metadata": meta}
    v = load_verified_artifact(_write_artifact(tmp_path, bundle, meta))
    with pytest.raises(ExplainabilityError, match="uncalibrated"):
        ChurnShapExplainer(v, world["parts"].train)


def test_creation_is_deterministic(verified, background):
    a, b = ChurnShapExplainer(verified, background), ChurnShapExplainer(verified, background)
    assert a.background_index == b.background_index
    assert a.base_value == b.base_value


def test_background_is_train_only_bounded_and_has_no_target(background, world, explainer):
    parts = world["parts"]
    idx = set(background.index)
    assert idx <= set(parts.train.index)
    assert not idx & set(parts.val.index) and not idx & set(parts.test.index)
    assert list(background.columns) == world["meta"]["feature_names"]
    assert "Churn" not in background.columns and "customerID" not in background.columns
    assert len(background) == 100 and len(explainer.background_raw) == 100
    assert set(explainer.background_index) == idx


def test_background_size_respects_config_and_data(world, verified):
    train = world["parts"].train
    assert len(select_background(train, world["meta"]["feature_names"], 25, SEED)) == 25
    assert len(select_background(train.head(10), world["meta"]["feature_names"], 100, SEED)) == 10
    ex = ChurnShapExplainer(verified, train, _cfg(background={"max_rows": 30}))
    assert len(ex.background_raw) == 30
    a = select_background(train, world["meta"]["feature_names"], 25, SEED)
    b = select_background(train, world["meta"]["feature_names"], 25, SEED)
    assert list(a.index) == list(b.index)
    assert list(a.index) != list(select_background(train, world["meta"]["feature_names"], 25, SEED + 1).index)


def test_background_rejects_target_and_bad_inputs(world):
    train, feats = world["parts"].train, world["meta"]["feature_names"]
    with pytest.raises(ExplainabilityError, match="target"):
        select_background(train, [*feats, "Churn"], 10, SEED, target="Churn")
    with pytest.raises(ExplainabilityError, match="max_rows"):
        select_background(train, feats, 0, SEED)
    with pytest.raises(ExplainabilityError, match="empty"):
        select_background(train.iloc[0:0], feats, 10, SEED)
    with pytest.raises(ExplainabilityError, match="lacks"):
        select_background(train.drop(columns=["tenure"]), feats, 10, SEED)


def test_load_train_background_checks_dataset_version(world, verified, tmp_path):
    other = tmp_path / "other.csv"
    world["df"].head(900).to_csv(other, index=False)
    with pytest.raises(ExplainabilityError, match="Dataset version"):
        load_train_background(other, world["spec"], verified)


# ============================================================================================ local explanation
def test_local_explanation_fields(explainer, records, world):
    e = explainer.explain(records.iloc[0].to_dict())
    assert isinstance(e, LocalExplanation)
    assert 0.0 <= e.prediction_probability <= 1.0
    assert e.prediction_probability == pytest.approx(world["model"].predict_proba(records.iloc[[0]])[0, 1])
    assert e.threshold == 0.34 and e.output_space == "log_odds"
    assert e.predicted_class == int(e.prediction_probability >= e.threshold)
    json.dumps(e.to_dict())                                   # JSON-serialisable, no numpy leaks


def test_predicted_class_follows_threshold_for_every_row(explainer, records, verified):
    exps = explainer.explain_many(records)
    pred = verified.artifact.predict(records)
    assert [e.predicted_class for e in exps] == pred.tolist()
    assert set(e.predicted_class for e in exps) == {0, 1}      # both sides of the threshold are exercised


def test_feature_count_names_and_signs(explainer, records):
    exps = explainer.explain_many(records)
    sources = explainer.feature_map.sources
    for e in exps:
        assert [f.source_feature for f in e.features].__len__() == len(sources)
        assert {f.source_feature for f in e.features} == set(sources)
        assert len({f.source_feature for f in e.features}) == len(e.features)
        assert not any("__" in f.source_feature or "=" in f.source_feature for f in e.features)
    allv = np.array([f.shap_value for e in exps for f in e.features])
    assert (allv > 0).any() and (allv < 0).any()                # signed, not absolute
    names = {f.source_feature for f in exps[0].features}
    assert {"Contract", "tenure", "PaymentMethod"} <= names
    assert {"tenure_group", "contract_risk", "service_count"} <= names  # engineered features appear by name


def test_features_sorted_by_absolute_contribution(explainer, records):
    e = explainer.explain(records.iloc[1].to_dict())
    keys = [(-round(abs(f.shap_value), 12), f.source_feature) for f in e.features]
    assert keys == sorted(keys)


def test_direction_labels_match_sign(explainer, records):
    for e in explainer.explain_many(records.head(10)):
        for f in e.features:
            assert f.direction in DIRECTIONS
            if f.shap_value > explainer.epsilon:
                assert f.direction == "increases_churn"
            elif f.shap_value < -explainer.epsilon:
                assert f.direction == "decreases_churn"
            else:
                assert f.direction == "neutral"


def test_neutral_label_with_large_epsilon(verified, background, records):
    ex = ChurnShapExplainer(verified, background, _cfg(direction_epsilon=1e6))
    assert {f.direction for f in ex.explain(records.iloc[0].to_dict()).features} == {"neutral"}


def test_raw_values_missing_and_engineered_flag(explainer, records):
    rec = records.iloc[0].to_dict()
    rec["TotalCharges"] = " "                                     # Telco-style blank
    e = explainer.explain(rec)
    by = {f.source_feature: f for f in e.features}
    assert by["Contract"].raw_value == rec["Contract"] and by["Contract"].is_engineered is False
    assert by["TotalCharges"].raw_value is None
    assert by["contract_risk"].is_engineered is True and by["tenure_group"].is_engineered is True


def test_interpretation_is_not_causal(explainer, records):
    note = explainer.explain(records.iloc[0].to_dict()).interpretation.lower()
    assert "not causes" in note and "caused the customer" not in note


# ============================================================================================== feature mapping
def test_one_hot_columns_map_to_source_feature(explainer):
    fm = explainer.feature_map
    contract = [n for n, s in zip(fm.encoded_names, fm.source_of, strict=True) if s == "Contract"]
    assert sorted(contract) == ["cat__Contract_Month-to-month", "cat__Contract_One year", "cat__Contract_Two year"]
    assert [fm.encoded_labels[i] for i in fm.groups["Contract"]] == [
        "Contract=Month-to-month", "Contract=One year", "Contract=Two year"]
    # engineered categorical feature (`tenure_group`) and numeric ones keep their own name
    assert all(fm.encoded_names[i].startswith("cat__tenure_group_") for i in fm.groups["tenure_group"])
    assert [fm.encoded_names[i] for i in fm.groups["tenure"]] == ["num__tenure"]
    assert "Contract" in fm.sources and "contract_risk" in fm.sources and "contract" not in fm.sources


def test_mapping_is_a_partition_and_aggregation_is_exact(explainer):
    fm = explainer.feature_map
    covered = np.concatenate([fm.groups[s] for s in fm.sources])
    assert sorted(covered.tolist()) == list(range(len(fm.encoded_names)))   # each column counted exactly once
    m = np.random.default_rng(0).normal(size=(7, len(fm.encoded_names)))
    agg = fm.aggregate(m)
    assert agg.shape == (7, len(fm.sources))
    np.testing.assert_allclose(agg.sum(axis=1), m.sum(axis=1), atol=1e-12)
    for j, s in enumerate(fm.sources):
        np.testing.assert_allclose(agg[:, j], m[:, [i for i, x in enumerate(fm.source_of) if x == s]].sum(axis=1))
    with pytest.raises(ExplainabilityError):
        fm.aggregate(m[:, :-1])


def test_mapping_is_derived_not_hard_coded():
    X = pd.DataFrame({"age": [1.0, 2.0, 3.0, 4.0], "colour": ["r", "g", "b", "r"], "size": ["s", "m", "s", "l"]})
    fm = build_feature_map(build_preprocessor().fit(X))
    assert fm.sources == ["age", "colour", "size"]
    assert [fm.encoded_labels[i] for i in fm.groups["colour"]] == ["colour=b", "colour=g", "colour=r"]
    assert len(fm.groups["size"]) == 3


def test_unsupported_encoder_is_refused():
    from sklearn.compose import ColumnTransformer
    from sklearn.preprocessing import OneHotEncoder
    X = pd.DataFrame({"c": ["a", "b", "a", "b"]})
    ct = ColumnTransformer([("cat", OneHotEncoder(drop="first", sparse_output=False), ["c"])]).fit(X)
    with pytest.raises(ExplainabilityError, match="Unsupported OneHotEncoder"):
        build_feature_map(ct)


# =================================================================================================== global
def _toy_map():
    return FeatureMap(["a1", "a2", "b", "c"], ["a=1", "a=2", "b", "c"], ["a", "a", "b", "c"], ["a", "b", "c"],
                      {"a": np.array([0, 1]), "b": np.array([2]), "c": np.array([3])})


def test_global_importance_is_mean_abs_of_source_level_shap(explainer, records):
    items = explainer.global_importance(records)
    assert items and len(items) == len(explainer.feature_map.sources)
    exps = explainer.explain_many(records)
    for it in items:
        manual = np.mean([abs(next(f.shap_value for f in e.features if f.source_feature == it.source_feature))
                          for e in exps])
        assert it.mean_abs_shap == pytest.approx(manual, abs=1e-12)
    assert [i.rank for i in items] == list(range(1, len(items) + 1))
    assert all(a.mean_abs_shap >= b.mean_abs_shap for a, b in zip(items, items[1:], strict=False))


def test_global_importance_aggregates_before_abs():
    m = np.array([[1.0, -1.0, 0.5, 0.0], [1.0, -1.0, 0.5, 0.0]])    # a's encoded columns cancel exactly
    by = {i.source_feature: i.mean_abs_shap for i in global_importance(_toy_map(), m)}
    assert by["a"] == 0.0 and by["b"] == 0.5


def test_global_importance_tie_break_and_determinism(explainer, records):
    m = np.array([[0.5, 0.0, 0.5, 0.5]])
    items = global_importance(_toy_map(), m)
    assert [i.source_feature for i in items] == ["a", "b", "c"]            # tie -> alphabetical
    m2 = np.array([[0.0, 0.0, 0.5, 0.9]])
    assert [i.source_feature for i in global_importance(_toy_map(), m2)] == ["c", "b", "a"]
    assert explainer.global_importance(records) == explainer.global_importance(records)
    with pytest.raises(ExplainabilityError):
        global_importance(_toy_map(), np.empty((0, 4)))


# =================================================================================================== drivers
def test_positive_and_negative_drivers(explainer, records):
    rec = records.iloc[0].to_dict()
    e = explainer.explain(rec)
    pos, neg = top_positive_drivers(e, 5), top_negative_drivers(e, 5)
    assert pos and neg
    assert all(f.shap_value > 0 and f.direction == "increases_churn" for f in pos)
    assert all(f.shap_value < 0 and f.direction == "decreases_churn" for f in neg)
    assert [f.shap_value for f in pos] == sorted((f.shap_value for f in pos), reverse=True)
    assert [f.shap_value for f in neg] == sorted(f.shap_value for f in neg)
    assert len(top_positive_drivers(e, 2)) == 2
    assert explainer.top_positive_drivers(rec, 3) == pos[:3]
    assert explainer.top_negative_drivers(rec, 3) == neg[:3]
    assert explainer.top_positive_drivers(rec, 3) == explainer.top_positive_drivers(rec, 3)   # deterministic


def test_driver_ordering_ties_neutral_and_n_validation():
    def f(name, v, d):
        return FeatureContribution(name, 1, v, d)
    e = LocalExplanation(0.5, 1, 0.34, 0.0, "log_odds", [
        f("b", 0.3, "increases_churn"), f("a", 0.3, "increases_churn"), f("z", 0.9, "increases_churn"),
        f("n", 0.0, "neutral"), f("d", -0.3, "decreases_churn"), f("c", -0.3, "decreases_churn"),
        f("e", -0.8, "decreases_churn")], 0.0, 0.0)
    assert [x.source_feature for x in top_positive_drivers(e, 10)] == ["z", "a", "b"]
    assert [x.source_feature for x in top_negative_drivers(e, 10)] == ["e", "c", "d"]
    for bad in (0, -1, True, 1.5):
        with pytest.raises(ValueError):
            top_positive_drivers(e, bad)


# ============================================================================================ reconstruction
def test_base_plus_shap_reconstructs_log_odds_and_probability(explainer, records, world):
    exps = explainer.explain_many(records)
    pipe = world["pipe"]
    z = pipe[:-1].transform(records)
    log_odds = pipe.named_steps["model"].decision_function(z)             # independent of the explainer
    tol = explainer.tolerance
    assert tol == load_config("explainability")["reconstruction"]["tolerance"]
    for e, lo, p in zip(exps, log_odds, world["model"].predict_proba(records)[:, 1], strict=True):
        assert e.base_value + sum(f.shap_value for f in e.features) == pytest.approx(lo, abs=tol)
        assert e.model_log_odds == pytest.approx(lo, abs=1e-12)
        assert e.reconstruction_error <= tol
        assert expit(e.base_value + sum(f.shap_value for f in e.features)) == pytest.approx(p, abs=tol)


def test_base_value_is_mean_background_log_odds(explainer, world):
    z = world["pipe"][:-1].transform(explainer.background_raw)
    mean_lo = float(world["pipe"].named_steps["model"].decision_function(z).mean())
    assert explainer.base_value == pytest.approx(mean_lo, abs=1e-9)


def test_broken_reconstruction_is_reported_not_hidden(verified, background, records):
    ex = ChurnShapExplainer(verified, background)
    ex.base_value += 0.5                                    # corrupt the base value
    with pytest.raises(ExplainabilityError, match="reconstruction failed"):
        ex.explain(records.iloc[0].to_dict())


def test_determinism_across_instances(verified, background, records):
    a = ChurnShapExplainer(verified, background).explain_many(records.head(5))
    b = ChurnShapExplainer(verified, background).explain_many(records.head(5))
    for x, y in zip(a, b, strict=True):
        assert [f.source_feature for f in x.features] == [f.source_feature for f in y.features]
        np.testing.assert_allclose([f.shap_value for f in x.features], [f.shap_value for f in y.features],
                                   atol=1e-12)
        assert x.prediction_probability == y.prediction_probability


# ============================================================================================= invalid input
def test_missing_feature_rejected(explainer, records):
    rec = records.iloc[0].to_dict()
    rec.pop("Contract")
    with pytest.raises(ExplainabilityInputError, match=r"Missing required feature.*Contract"):
        explainer.explain(rec)
    with pytest.raises(ExplainabilityInputError, match="Missing required"):
        explainer.global_importance(records.drop(columns=["tenure", "gender"]))


@pytest.mark.parametrize("col,value,match", [
    ("tenure", "abc", "not a valid number"),
    ("MonthlyCharges", float("inf"), "finite"),
    ("MonthlyCharges", float("-inf"), "finite"),
    ("tenure", True, "boolean"),
    ("Contract", ["a", "b"], "single scalar"),
    ("tenure", {"x": 1}, "single scalar"),
])
def test_malformed_values_rejected(explainer, records, col, value, match):
    rec = records.iloc[0].to_dict()
    rec[col] = value
    with pytest.raises(ExplainabilityInputError, match=match):
        explainer.explain(rec)


@pytest.mark.parametrize("bad", [None, "text", 5, [], pd.DataFrame(), [1, 2], np.array([1, 2])])
def test_malformed_containers_and_empty_rejected(explainer, bad):
    with pytest.raises(ExplainabilityInputError):
        explainer.explain(bad)


def test_duplicate_columns_and_multi_row_rejected(explainer, records):
    dup = pd.concat([records.head(1), records.head(1)[["tenure"]]], axis=1)
    with pytest.raises(ExplainabilityInputError, match="Duplicate"):
        explainer.explain(dup)
    with pytest.raises(ExplainabilityInputError, match="exactly one record"):
        explainer.explain(records.head(2))


def test_raw_records_accepted_without_manual_encoding(explainer, records):
    rec = {**records.iloc[0].to_dict(), "customerID": "X-1", "Churn": "Yes"}   # extras (id/target) are ignored
    e1, e2 = explainer.explain(rec), explainer.explain(pd.DataFrame([rec]))
    assert e1.prediction_probability == e2.prediction_probability
    assert explainer.explain_many([rec, rec])[1].prediction_probability == e1.prediction_probability


def test_validate_input_returns_model_columns_in_order(world):
    feats = world["meta"]["feature_names"]
    pipe = world["pipe"]
    coer = pipe.named_steps["coerce"]
    df = validate_input(world["parts"].val.head(3), feats, coer.numeric, coer.categorical)
    assert list(df.columns) == feats and len(df) == 3 and list(df.index) == [0, 1, 2]


# ============================================================================ real locked artifact (integration)
REAL_MODEL = Path("models/trichurn_churn_model_v2.0.0.joblib")
REAL_CSV = Path("ml/data/raw/telco_churn.csv")


@pytest.mark.integration
@pytest.mark.skipif(not (REAL_MODEL.exists() and REAL_CSV.exists()), reason="needs models/ and `make data`")
def test_real_locked_artifact_explanations(spec):
    v = load_verified_artifact(REAL_MODEL)
    side = json.loads(REAL_MODEL.with_name(f"{REAL_MODEL.stem}.metadata.json").read_text())
    assert v.sha256 == side["artifact_sha256"]
    assert side["model_name"] == "logistic_regression" and side["calibration"]["method"] == "none"
    assert v.artifact.threshold == 0.34
    bg = load_train_background(REAL_CSV, spec, v)
    assert len(bg) == 100 and "Churn" not in bg.columns
    ex = ChurnShapExplainer(v, bg)
    assert len(ex.feature_map.encoded_names) == 58
    assert {"Contract", "tenure", "tenure_group", "contract_risk"} <= set(ex.feature_map.sources)
    df = pd.read_csv(REAL_CSV).head(200)
    exps = ex.explain_many(df)
    assert np.array_equal([e.predicted_class for e in exps], v.artifact.predict(df))
    assert max(e.reconstruction_error for e in exps) < 1e-6
    assert all(math.isfinite(f.shap_value) for e in exps for f in e.features)
    imp = ex.global_importance(df)
    assert imp[0].rank == 1 and imp[0].mean_abs_shap >= imp[-1].mean_abs_shap
