"""Phase 5 - K-Means determinism, candidate-K evaluation, K selection, assignment, label-permutation handling."""
import dataclasses
import inspect

import numpy as np
import pytest
from sklearn.metrics import (
    adjusted_rand_score,
    calinski_harabasz_score,
    davies_bouldin_score,
    silhouette_score,
)

from ml.errors import SegmentationConfigError, SegmentationInputError
from ml.segmentation import (
    CustomerAssignment,
    KCandidate,
    canonical_order,
    clusterings_equivalent,
    evaluate_k_candidates,
    fit_segmentation,
    load_segmentation_config,
    select_k,
)
from ml.segmentation.clustering import make_kmeans
from tests.conftest import make_segment_frame


@pytest.fixture(scope="module")
def frame():
    return make_segment_frame(n_per_group=120, seed=11)


@pytest.fixture(scope="module")
def cfg():
    return load_segmentation_config()


@pytest.fixture(scope="module")
def fitted(frame, cfg, spec, features_cfg):
    return fit_segmentation(frame, spec, cfg, features_cfg, 42)


# ------------------------------------------------------------------------------------------------ determinism
def test_same_seed_gives_identical_centroids_and_assignments(frame, cfg, spec, features_cfg, fitted):
    again, sel = fit_segmentation(frame, spec, cfg, features_cfg, 42)
    model, selection = fitted
    assert np.array_equal(again.centers, model.centers) and again.k == model.k
    assert np.array_equal(again.assign(frame)[0], model.assign(frame)[0])
    assert np.array_equal(again.assign(frame)[1], model.assign(frame)[1])
    assert sel.to_dict() == selection.to_dict()


def test_row_order_does_not_change_which_customers_group_together(frame, cfg, spec, features_cfg, fitted):
    shuffled = frame.sample(frac=1.0, random_state=5)
    other, _ = fit_segmentation(shuffled, spec, cfg, features_cfg, 42, k=3)
    ids = dict(zip(frame["customerID"], fitted[0].assign(frame)[0], strict=True))
    ids2 = dict(zip(shuffled["customerID"], other.assign(shuffled)[0], strict=True))
    a = [ids[c] for c in frame["customerID"]]
    b = [ids2[c] for c in frame["customerID"]]
    assert clusterings_equivalent(np.array(a), np.array(b))


def test_kmeans_parameters_come_from_configuration(cfg):
    km = make_kmeans(4, cfg.kmeans, 9)
    assert (km.n_clusters, km.init, km.n_init, km.max_iter, km.tol, km.algorithm, km.random_state) == \
           (4, "k-means++", 10, 300, 1e-4, "lloyd", 9)
    custom = load_segmentation_config({"kmeans": {"init": "random", "n_init": 3, "max_iter": 50, "tol": 1e-2}})
    km = make_kmeans(2, custom.kmeans, 1)
    assert (km.init, km.n_init, km.max_iter, km.tol) == ("random", 3, 50, 1e-2)


# ------------------------------------------------------------------------------- candidate K / selection
def test_candidate_metrics_match_sklearn_and_report_configured_extras(frame, cfg, spec, features_cfg, fitted):
    model = fitted[0]
    Z = model.transform(frame)
    cands = evaluate_k_candidates(Z, cfg.k_selection, cfg.kmeans, 42)
    assert [c.k for c in cands] == list(cfg.k_selection.candidates)
    for c in cands:
        km = make_kmeans(c.k, cfg.kmeans, 42).fit(Z)
        assert c.silhouette == pytest.approx(silhouette_score(Z, km.labels_))
        assert -1.0 <= c.silhouette <= 1.0
        assert c.extra["inertia"] == pytest.approx(km.inertia_)
        assert c.extra["calinski_harabasz"] == pytest.approx(calinski_harabasz_score(Z, km.labels_))
        assert c.extra["davies_bouldin"] == pytest.approx(davies_bouldin_score(Z, km.labels_))
        assert c.min_cluster_share == pytest.approx(np.bincount(km.labels_).min() / len(Z))


def test_report_metrics_are_optional_and_configurable(frame, spec, features_cfg, fitted):
    custom = load_segmentation_config({"k_selection": {"report_metrics": ["inertia"], "candidates": [2, 3]}})
    cands = evaluate_k_candidates(fitted[0].transform(frame), custom.k_selection, custom.kmeans, 42)
    assert [set(c.extra) for c in cands] == [{"inertia"}, {"inertia"}]


def test_well_separated_data_selects_the_true_number_of_groups(fitted):
    model, selection = fitted
    assert selection.selected_k == 3 == model.k and selection.method == "silhouette"
    best = max(selection.candidates, key=lambda c: c.silhouette)
    assert best.k == 3 and selection.best_silhouette_k == 3
    assert "highest silhouette" in selection.rationale


def test_eligibility_rules_and_business_range_override_the_mathematical_optimum(cfg):
    cands = (KCandidate(2, 0.90, 0.40, False, "range", {}), KCandidate(3, 0.60, 0.30, True, None, {}),
             KCandidate(4, 0.70, 0.30, True, None, {}), KCandidate(5, 0.99, 0.01, False, "small", {}))
    sel = select_k(cands, cfg.k_selection)
    assert sel.selected_k == 4 and sel.best_silhouette_k == 5          # best eligible, not best overall
    assert "unconstrained silhouette optimum is K=5" in sel.rationale


def test_silhouette_ties_go_to_the_smaller_k(cfg):
    cands = (KCandidate(3, 0.5, 0.3, True, None, {}), KCandidate(4, 0.5, 0.3, True, None, {}),
             KCandidate(5, 0.5, 0.3, True, None, {}))
    assert select_k(cands, cfg.k_selection).selected_k == 3


def test_candidates_are_flagged_by_range_and_cluster_share(frame, spec, features_cfg, fitted):
    custom = load_segmentation_config({"k_selection": {"min_k": 4, "max_k": 5, "min_cluster_share": 0.45}})
    cands = evaluate_k_candidates(fitted[0].transform(frame), custom.k_selection, custom.kmeans, 42)
    by_k = {c.k: c for c in cands}
    assert not by_k[3].eligible and "outside the allowed business range" in by_k[3].ineligible_reason
    assert not by_k[4].eligible and "smallest cluster holds" in by_k[4].ineligible_reason
    with pytest.raises(SegmentationConfigError, match="No candidate K satisfies"):
        select_k(cands, custom.k_selection)


def test_fixed_k_is_honoured_and_the_unconstrained_optimum_is_still_reported(frame, spec, features_cfg, fitted):
    custom = load_segmentation_config({"k_selection": {"method": "fixed", "fixed_k": 5}})
    model, sel = fit_segmentation(frame, spec, custom, features_cfg, 42)
    assert model.k == 5 and sel.method == "fixed" and sel.selected_k == 5
    assert "fixed in configuration" in sel.rationale and "K=3" in sel.rationale
    assert len(sel.candidates) == len(custom.k_selection.candidates)


def test_explicit_k_skips_selection(frame, cfg, spec, features_cfg):
    model, sel = fit_segmentation(frame, spec, cfg, features_cfg, 42, k=4)
    assert model.k == 4 and sel is None


def test_too_few_customers_for_any_candidate_is_a_clear_error(frame, cfg, spec, features_cfg, fitted):
    Z = fitted[0].transform(frame)[:2]
    with pytest.raises(SegmentationInputError, match="too few for candidate K"):
        evaluate_k_candidates(Z, cfg.k_selection, cfg.kmeans, 42)


def test_silhouette_subsampling_is_seeded(frame, fitted):
    custom = load_segmentation_config({"k_selection": {"silhouette_sample_size": 150, "candidates": [3]}})
    Z = fitted[0].transform(frame)
    a = evaluate_k_candidates(Z, custom.k_selection, custom.kmeans, 42)
    b = evaluate_k_candidates(Z, custom.k_selection, custom.kmeans, 42)
    assert a[0].silhouette == b[0].silhouette


# ------------------------------------------------------------------------------- assignment / distance
def test_assignment_is_nearest_centroid_and_distance_is_euclidean(frame, fitted):
    model = fitted[0]
    ids, dist = model.assign(frame)
    Z = model.transform(frame)
    full = np.linalg.norm(Z[:, None, :] - model.centers[None, :, :], axis=2)
    assert np.array_equal(ids, full.argmin(axis=1)) and np.allclose(dist, full.min(axis=1))
    assert ids.min() == 0 and ids.max() == model.k - 1 and (dist >= 0).all()
    assert np.allclose(dist, np.linalg.norm(Z - model.centers[ids], axis=1))


def test_assignment_matches_sklearn_predict_through_the_canonical_mapping(frame, fitted):
    model = fitted[0]
    raw = model.kmeans.predict(model.transform(frame))
    assert np.array_equal(model.raw_label_to_segment[raw], model.assign(frame)[0])
    assert np.array_equal(np.sort(model.raw_label_to_segment), np.arange(model.k))     # a true permutation


def test_distance_to_centroid_is_a_distance_not_a_probability():
    fields = {f.name for f in dataclasses.fields(CustomerAssignment)}
    assert fields == {"customer_id", "segment_id", "segment_name", "distance_to_centroid"}
    assert not any("prob" in f for f in fields)
    assert "NOT a probability" in inspect.getdoc(CustomerAssignment)


def test_recovers_the_true_archetypes(frame, fitted):
    ids = fitted[0].assign(frame)[0]
    assert clusterings_equivalent(ids, frame["group"].to_numpy())
    assert adjusted_rand_score(ids, frame["group"]) == pytest.approx(1.0)


def test_new_customers_are_assigned_without_refitting(frame, cfg, spec, features_cfg, fitted):
    model = fitted[0]
    before = model.centers.copy()
    new = make_segment_frame(n_per_group=15, seed=99)
    ids, _ = model.assign(new)
    assert clusterings_equivalent(ids, new["group"].to_numpy())
    assert np.array_equal(model.centers, before)            # assigning customers never moves the centroids


# ------------------------------------------------------------------------- label permutation handling
def test_canonical_order_is_invariant_to_label_permutation():
    rng = np.random.default_rng(0)
    centers = rng.normal(size=(5, 4))
    ref = centers[canonical_order(centers)]
    for _ in range(25):
        perm = rng.permutation(5)
        assert np.array_equal(centers[perm][canonical_order(centers[perm])], ref)


def test_canonical_order_breaks_ties_on_later_features_and_ignores_float_noise():
    c = np.array([[1.0, 5.0], [1.0 + 1e-12, 2.0], [0.5, 9.0]])
    order = canonical_order(c)
    assert order.tolist() == [2, 1, 0]


def test_clusterings_equivalent_handles_relabelling_merging_and_splitting():
    a = np.array([0, 0, 1, 1, 2, 2])
    assert clusterings_equivalent(a, np.array([2, 2, 0, 0, 1, 1]))
    assert not clusterings_equivalent(a, np.array([0, 0, 0, 0, 1, 1]))          # merged
    assert not clusterings_equivalent(a, np.array([0, 1, 1, 1, 2, 2]))          # moved a customer
    assert not clusterings_equivalent(a, a[:-1])


def test_different_seeds_with_different_raw_labels_give_identical_segment_ids(frame, cfg, spec, features_cfg):
    """sklearn's raw label order depends on the seed; segment_id (canonical order) must not."""
    models = [fit_segmentation(frame, spec, cfg, features_cfg, seed, k=3)[0] for seed in range(12)]
    maps = {tuple(m.raw_label_to_segment.tolist()) for m in models}
    assert len(maps) > 1, "need at least two seeds whose raw K-Means label orders differ"
    ref = models[0].assign(frame)[0]
    for m in models[1:]:
        assert np.array_equal(m.assign(frame)[0], ref)
        assert np.allclose(m.centers, models[0].centers, atol=1e-6)


def test_permuting_the_model_centroids_does_not_change_the_partition(frame, fitted):
    """A model whose centroids are stored in another order defines the same partition (labels just renamed)."""
    model = fitted[0]
    ids = model.assign(frame)[0]
    perm = np.array([2, 0, 1])
    permuted = dataclasses.replace(model, centers=model.centers[perm])
    pids, pdist = permuted.assign(frame)
    assert clusterings_equivalent(ids, pids) and not np.array_equal(ids, pids)
    assert np.allclose(pdist, model.assign(frame)[1])
