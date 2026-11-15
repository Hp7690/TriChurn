"""Phase 5 - configuration, clustering feature selection, target exclusion and preprocessing."""
import copy

import numpy as np
import pandas as pd
import pytest

from ml.config import load_config
from ml.errors import SegmentationConfigError, SegmentationInputError
from ml.segmentation import (
    SegmentationFeatureBuilder,
    build_preprocessor,
    load_segmentation_config,
    parse_segmentation_config,
    resolve_seed,
    validate_feature_set,
)
from tests.conftest import make_segment_frame


def raw_cfg(**changes):
    raw = copy.deepcopy(load_config("segmentation"))
    for path, value in changes.items():
        node = raw
        *parents, leaf = path.split("__")
        for p in parents:
            node = node[p]
        node[leaf] = value
    return raw


# ---------------------------------------------------------------------------------------------------- config
def test_default_config_matches_documented_choices():
    cfg = load_segmentation_config()
    assert cfg.features.all == ("tenure", "MonthlyCharges", "TotalCharges", "service_count", "contract_risk")
    assert (cfg.scaling, cfg.imputation, cfg.kmeans.init, cfg.kmeans.n_init, cfg.kmeans.max_iter) == \
           ("standard", "median", "k-means++", 10, 300)
    assert cfg.k_selection.method == "silhouette" and cfg.k_selection.candidates == (2, 3, 4, 5, 6, 7, 8)
    assert (cfg.k_selection.min_k, cfg.k_selection.max_k) == (3, 6)
    assert cfg.model_version == "5.0.0" and cfg.artifact_name == "trichurn_segmentation"


def test_seed_null_inherits_the_project_seed(training_cfg):
    assert load_segmentation_config().seed is None
    assert resolve_seed(load_segmentation_config(), training_cfg) == training_cfg["seed"] == 42
    assert resolve_seed(load_segmentation_config({"seed": 7}), training_cfg) == 7


@pytest.mark.parametrize("changes, message", [
    ({"scaling": "robust"}, "scaling must be one of"),
    ({"imputation": "zero"}, "imputation must be one of"),
    ({"kmeans__init": "forgy"}, "kmeans.init"),
    ({"kmeans__n_init": 0}, "kmeans.n_init"),
    ({"kmeans__max_iter": 1.5}, "kmeans.max_iter"),
    ({"k_selection__method": "elbow"}, "k_selection.method"),
    ({"k_selection__method": "fixed"}, "fixed_k is not set"),
    ({"k_selection__method": "fixed", "k_selection__fixed_k": 9}, "must be one of the candidates"),
    ({"k_selection__candidates": []}, "non-empty"),
    ({"k_selection__candidates": [1, 2]}, "k_selection.candidates"),
    ({"k_selection__min_k": 7}, "min_k must be <= max_k"),
    ({"k_selection__min_cluster_share": 0.9}, "min_cluster_share"),
    ({"k_selection__report_metrics": ["purity"]}, "report_metrics"),
    ({"naming__value__low_max_ratio": 2.0}, "low/new ratios"),
    ({"naming__risk__stable_max_probability": 0.9, "naming__risk__high_min_probability": 0.3}, "stable_max"),
    ({"priority__weights": {"vibes": 1.0}}, "priority.weights"),
    ({"priority__weights": {"value_at_risk_share": 0.0}}, "positive weight"),
    ({"priority__weights": {"value_at_risk_share": -1.0}}, "must be >= 0"),
    ({"priority__tiers": [{"name": "A", "min_score": 0.1}]}, "ending at 0"),
    ({"priority__tiers": [{"name": "A", "min_score": 0.0}, {"name": "B", "min_score": 0.5}]}, "descending"),
    ({"features__numeric": [], "features__engineered": []}, "at least one clustering feature"),
    ({"features__numeric": ["tenure", "tenure"]}, "duplicates"),
])
def test_invalid_configuration_is_rejected_with_a_clear_error(changes, message):
    with pytest.raises(SegmentationConfigError, match=message):
        parse_segmentation_config(raw_cfg(**changes))


def test_missing_section_is_rejected():
    raw = raw_cfg()
    del raw["priority"]
    with pytest.raises(SegmentationConfigError, match="missing 'segmentation.priority'"):
        parse_segmentation_config(raw)


def test_config_objects_are_immutable():
    cfg = load_segmentation_config()
    with pytest.raises(AttributeError):
        cfg.scaling = "none"
    with pytest.raises(AttributeError):
        cfg.k_selection.max_k = 99


# ------------------------------------------------------------------------------- feature selection / exclusion
@pytest.mark.parametrize("forbidden", ["Churn", "churn", "CHURN", "churn_probability", "clv", "value_at_risk",
                                       "expected_net_benefit", "intervention_decision", "risk_band"])
def test_target_and_model_or_business_outputs_cannot_be_configured_as_clustering_features(forbidden):
    with pytest.raises(SegmentationConfigError, match="Forbidden clustering features"):
        parse_segmentation_config(raw_cfg(features__numeric=["tenure", forbidden]))
    with pytest.raises(SegmentationConfigError, match="Forbidden clustering features"):
        parse_segmentation_config(raw_cfg(features__engineered=[forbidden]))


def test_dataset_target_and_id_are_refused_even_if_the_forbidden_list_is_emptied(spec):
    cfg = parse_segmentation_config(raw_cfg(features__forbidden=["nothing_special"],
                                            features__numeric=["tenure", spec.target]))
    with pytest.raises(SegmentationConfigError, match="not allowed"):
        validate_feature_set(cfg.features, spec)
    cfg = parse_segmentation_config(raw_cfg(features__forbidden=["nothing_special"],
                                            features__numeric=["tenure", spec.id_column]))
    with pytest.raises(SegmentationConfigError, match="not allowed"):
        build_preprocessor(cfg, load_config("features"), spec)


def test_default_feature_set_is_valid_and_contains_no_target_or_output(spec):
    cfg = load_segmentation_config()
    validate_feature_set(cfg.features, spec)
    lowered = {f.lower() for f in cfg.features.all}
    assert not lowered & {spec.target.lower(), spec.id_column.lower(), *cfg.features.forbidden}


def test_builder_output_is_exactly_the_configured_features_in_order(spec, features_cfg):
    cfg, df = load_segmentation_config(), make_segment_frame()
    pre = build_preprocessor(cfg, features_cfg, spec).fit(df)
    built = pre.named_steps["features"].transform(df)
    assert list(built.columns) == list(cfg.features.all) and len(built) == len(df)
    assert built.dtypes.eq("float64").all()
    assert list(pre.named_steps["features"].get_feature_names_out()) == list(cfg.features.all)
    # engineered features come from the Phase 1 FeatureEngineer (8 services total; archetype 3 has all 8)
    assert built.loc[df["group"] == 2, "service_count"].eq(8).all()
    assert set(built.loc[df["group"] == 0, "contract_risk"]) == {2.0}
    assert set(built.loc[df["group"] == 2, "contract_risk"]) == {0.0}


def test_target_column_cannot_influence_the_clustering_matrix(spec, features_cfg):
    cfg, df = load_segmentation_config(), make_segment_frame()
    pre = build_preprocessor(cfg, features_cfg, spec).fit(df)
    Z = pre.transform(df)
    shuffled = df.assign(Churn=np.random.default_rng(1).permutation(df["Churn"].to_numpy()))
    flipped = df.assign(Churn=df["Churn"].map({"Yes": "No", "No": "Yes"}))
    no_target = df.drop(columns=["Churn"])
    for variant in (shuffled, flipped, no_target):
        assert np.array_equal(pre.transform(variant), Z)
    # fitting without any target column at all also works and gives the same preprocessing
    other = build_preprocessor(cfg, features_cfg, spec).fit(no_target)
    assert np.array_equal(other.transform(df), Z)


def test_builder_rejects_missing_columns_and_unbuildable_engineered_features(spec, features_cfg):
    cfg, df = load_segmentation_config(), make_segment_frame()
    with pytest.raises(SegmentationInputError, match="missing clustering columns"):
        build_preprocessor(cfg, features_cfg, spec).fit(df.drop(columns=["tenure"]))
    pre = build_preprocessor(cfg, features_cfg, spec).fit(df)
    with pytest.raises(SegmentationInputError, match="missing clustering columns"):
        pre.transform(df.drop(columns=["MonthlyCharges"]))
    with pytest.raises(SegmentationInputError, match="cannot be built"):
        build_preprocessor(cfg, features_cfg, spec).fit(df.drop(columns=["Contract"]))


# --------------------------------------------------------------------------------------------- preprocessing
def test_imputer_uses_train_median_and_blank_total_charges_become_numbers(spec, features_cfg):
    cfg, df = load_segmentation_config({"scaling": "none"}), make_segment_frame()
    pre = build_preprocessor(cfg, features_cfg, spec).fit(df)
    raw_total = pd.to_numeric(df["TotalCharges"], errors="coerce")
    assert raw_total.isna().sum() > 0
    assert pre.named_steps["impute"].statistics_[2] == pytest.approx(raw_total.median())
    Z = pre.transform(df)
    assert np.isfinite(Z).all()
    assert Z[raw_total.isna().to_numpy(), 2] == pytest.approx(raw_total.median())


def test_standard_scaling_is_fitted_on_train_and_centres_it(spec, features_cfg):
    cfg, df = load_segmentation_config(), make_segment_frame()
    pre = build_preprocessor(cfg, features_cfg, spec).fit(df)
    Z = pre.transform(df)
    assert np.allclose(Z.mean(axis=0), 0, atol=1e-9) and np.allclose(Z.std(axis=0), 1, atol=1e-9)


def test_minmax_and_none_scaling(spec, features_cfg):
    df = make_segment_frame()
    mm = build_preprocessor(load_segmentation_config({"scaling": "minmax"}), features_cfg, spec).fit(df).transform(df)
    assert mm.min() == pytest.approx(0) and mm.max() == pytest.approx(1)
    raw = build_preprocessor(load_segmentation_config({"scaling": "none"}), features_cfg, spec).fit(df).transform(df)
    assert raw[:, 0].tolist() == df["tenure"].astype(float).tolist()


def test_preprocessing_is_fitted_on_the_training_frame_only(spec, features_cfg):
    """Transforming other customers never changes what was learned (imputation values / scaling)."""
    cfg, df = load_segmentation_config(), make_segment_frame(seed=3)
    train, other = df.iloc[:240], df.iloc[240:].assign(tenure=9999, MonthlyCharges=1e6)
    pre = build_preprocessor(cfg, features_cfg, spec).fit(train)
    before = (pre.named_steps["impute"].statistics_.copy(), pre.named_steps["scale"].mean_.copy(),
              pre.named_steps["scale"].scale_.copy())
    pre.transform(other)
    after = (pre.named_steps["impute"].statistics_, pre.named_steps["scale"].mean_, pre.named_steps["scale"].scale_)
    assert all(np.array_equal(a, b) for a, b in zip(before, after, strict=True))
    refit = build_preprocessor(cfg, features_cfg, spec).fit(train)
    assert np.array_equal(refit.transform(train), pre.transform(train))


def test_builder_is_clonable_and_has_no_hidden_state_before_fit():
    from sklearn.base import clone
    b = SegmentationFeatureBuilder(("tenure",), ("service_count",), load_config("features"))
    c = clone(b)
    assert c.numeric == b.numeric and not hasattr(c, "feature_names_")
