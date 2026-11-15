"""Phase 5 - segment profiles, business aggregation, naming, priority and strategy (Phase 4 reuse).

The scenario is controlled: three archetypes (see conftest.ARCHETYPES) with fixed churn probabilities, scored by the
REAL Phase 4 ``BusinessEngine``. Expected numbers are recomputed here from the frame and the YAML figures.
"""
import dataclasses

import numpy as np
import pytest

from ml.business import INTERVENE, BusinessEngine, load_business_config
from ml.config import load_config
from ml.errors import SegmentationConfigError, SegmentationInputError
from ml.segmentation import (
    SegmentationResult,
    assign_customers,
    build_assignments,
    fit_segmentation,
    load_segmentation_config,
    profile_segments,
    run_segmentation,
)
from ml.segmentation.profiling import (
    _Aggregate,
    name_segments,
    priority_scores,
    priority_tier,
    resolve_risk_threshold,
)
from tests.conftest import make_segment_frame

ZERO_WEIGHTS = {"value_at_risk_share": 0.0, "total_enb_share": 0.0, "avg_churn_probability": 0.0,
                "intervention_rate": 0.0}


def only(**weights):
    """Config override that puts weight ONLY on the named priority metrics (overrides are deep-merged)."""
    return {"priority": {"weights": {**ZERO_WEIGHTS, **weights}}}


PROB = {0: 0.80, 1: 0.40, 2: 0.10}        # archetype -> churn probability fed to Phase 4
THRESHOLD = 0.34


@pytest.fixture(scope="module")
def world(spec, features_cfg, training_cfg):
    frame = make_segment_frame(n_per_group=60, seed=5)
    cfg, business = load_segmentation_config(), load_business_config()
    probs = frame["group"].map(PROB).to_numpy()
    engine = BusinessEngine(business, THRESHOLD)
    result = run_segmentation(frame, probs, engine, spec, cfg, features_cfg, training_cfg)
    return {"frame": frame, "cfg": cfg, "business": business, "probs": probs, "engine": engine, "result": result,
            "spec": spec, "features": features_cfg, "training": training_cfg}


def by_group(world):
    """segment profile for each archetype (found through the customers, not through cluster numbers)."""
    frame, res = world["frame"], world["result"]
    out = {}
    for g in range(3):
        sid = int(res.segment_ids[(frame["group"] == g).to_numpy()][0])
        out[g] = next(p for p in res.profiles if p.segment_id == sid)
    return out


def test_result_shape_and_clustering_recovered_the_archetypes(world):
    res: SegmentationResult = world["result"]
    assert res.model.k == 3 and len(res.profiles) == 3 and len(res.assignments) == len(world["frame"])
    assert sorted(p.segment_id for p in res.profiles) == [0, 1, 2]
    assert len({p.segment_id for p in by_group(world).values()}) == 3


# ------------------------------------------------------------------------------- aggregation / reuse of Phase 4
def test_profile_fields_equal_independent_arithmetic(world):
    frame, business = world["frame"], load_config("business")
    lifetime = business["clv"]["lifetime_months_by_segment"]
    for g, prof in by_group(world).items():
        sub = frame[frame["group"] == g]
        clv = sub["MonthlyCharges"] * sub["Contract"].map(lifetime)
        p = PROB[g]
        assert prof.customer_count == len(sub) == 60 and prof.customer_pct == pytest.approx(60 / len(frame))
        assert prof.avg_tenure == pytest.approx(sub["tenure"].mean())
        assert prof.avg_monthly_charges == pytest.approx(sub["MonthlyCharges"].mean())
        assert prof.avg_total_charges == pytest.approx(np.nanmean(
            np.array([float(v) if str(v).strip() else np.nan for v in sub["TotalCharges"]])))
        assert prof.avg_churn_probability == pytest.approx(p)
        assert prof.avg_clv == pytest.approx(clv.mean()) and prof.total_clv == pytest.approx(clv.sum())
        assert prof.total_value_at_risk == pytest.approx(clv.sum() * p)


def test_business_figures_are_the_phase4_profiles_aggregated_not_recomputed(world):
    res = world["result"]
    for prof in res.profiles:
        mine = [b for b, s in zip(res.business_profiles, res.segment_ids, strict=True) if s == prof.segment_id]
        assert prof.total_clv == pytest.approx(sum(b.clv for b in mine))
        assert prof.total_value_at_risk == pytest.approx(sum(b.value_at_risk for b in mine))
        assert prof.total_enb == pytest.approx(sum(b.expected_net_benefit for b in mine))
        assert prof.avg_enb == pytest.approx(np.mean([b.expected_net_benefit for b in mine]))
        treated = sum(b.intervention_decision == INTERVENE for b in mine)
        assert prof.intervention_count == treated and prof.intervention_rate == pytest.approx(treated / len(mine))
        assert prof.avg_churn_probability == pytest.approx(np.mean([b.churn_probability for b in mine]))
    assert sum(p.customer_count for p in res.profiles) == len(world["frame"])
    assert sum(p.customer_pct for p in res.profiles) == pytest.approx(1.0)


def test_phase4_decisions_drive_the_intervention_rate(world):
    g = by_group(world)
    assert g[0].intervention_rate == 0.0          # high risk but CLV (~360) is below the 500 policy floor
    assert g[1].intervention_rate == 1.0          # p 0.40 >= 0.34, CLV ~1440, positive ENB
    assert g[2].intervention_rate == 0.0          # p 0.10 below the model threshold
    assert g[1].total_enb > 0 and g[0].total_enb == g[2].total_enb == 0.0


def test_changing_the_business_config_changes_the_segment_metrics(world):
    """Intervention rate / ENB are not computed in Phase 5: they follow whatever Phase 4 decides."""
    strict = BusinessEngine(load_business_config({"policy": {"min_customer_value": 10_000}}), THRESHOLD)
    res = run_segmentation(world["frame"], world["probs"], strict, world["spec"], world["cfg"], world["features"],
                           world["training"])
    assert all(p.intervention_rate == 0.0 and p.total_enb == 0.0 for p in res.profiles)
    assert all(p.strategy.primary_action_id == "no_action" for p in res.profiles)
    relaxed = BusinessEngine(load_business_config({"policy": {"min_customer_value": 0}}), THRESHOLD)
    res2 = run_segmentation(world["frame"], world["probs"], relaxed, world["spec"], world["cfg"], world["features"],
                            world["training"])
    assert next(p for p in res2.profiles if p.avg_churn_probability == pytest.approx(0.8)).intervention_rate > 0


def test_missing_total_charges_are_ignored_in_the_average(world):
    frame = world["frame"]
    blank = frame["TotalCharges"].astype(str).str.strip() == ""
    assert blank.any()
    for g, prof in by_group(world).items():
        sub = frame[(frame["group"] == g) & ~blank]
        assert prof.avg_total_charges == pytest.approx(sub["TotalCharges"].astype(float).mean())


# -------------------------------------------------------------------------------------------------- naming
def test_names_are_derived_from_measured_characteristics(world):
    g = by_group(world)
    assert g[2].segment_name == "High Value / Stable" and (g[2].value_label, g[2].risk_label) == \
           ("High Value", "Stable")
    # archetypes 0 and 1 are both Low Value / High Risk -> disambiguated by measured tenure, not by id
    assert g[0].segment_name == "Low Value / High Risk (New)"
    assert g[1].segment_name == "Low Value / High Risk (Mid-Tenure)"
    assert len({p.segment_name for p in world["result"].profiles}) == 3


def test_naming_thresholds_come_from_configuration(world):
    a = [_agg(0, avg_clv=2000, avg_prob=0.5), _agg(1, avg_clv=1000, avg_prob=0.1), _agg(2, avg_clv=100, avg_prob=0.25)]
    base = load_segmentation_config().naming
    names = name_segments(a, base, THRESHOLD)
    assert [names[i][0] for i in range(3)] == ["High Value / High Risk", "Mid Value / Stable",
                                               "Low Value / Moderate Risk"]
    loose = load_segmentation_config({"naming": {"value": {"high_min_ratio": 5.0, "low_max_ratio": 0.0},
                                                 "risk": {"high_min_probability": 0.9}}}).naming
    assert [name_segments(a, loose, THRESHOLD)[i][1:] for i in range(3)] == [("Mid Value", "Moderate Risk"),
                                                                              ("Mid Value", "Stable"),
                                                                              ("Mid Value", "Moderate Risk")]


def test_model_threshold_sentinel_in_naming(world):
    naming = load_segmentation_config().naming
    assert resolve_risk_threshold(naming, 0.34) == 0.34
    with pytest.raises(SegmentationInputError, match="model_threshold"):
        resolve_risk_threshold(naming, None)
    fixed = load_segmentation_config({"naming": {"risk": {"high_min_probability": 0.6}}}).naming
    assert resolve_risk_threshold(fixed, None) == 0.6


def test_identical_labels_get_stable_rank_suffixes_independent_of_ids():
    naming = load_segmentation_config({"naming": {"value": {"high_min_ratio": 0.0, "low_max_ratio": 0.0},
                                                  "risk": {"high_min_probability": 0.0, "stable_max_probability": 0.0},
                                                  "tenure": {"established_min_ratio": 0.0, "new_max_ratio": 0.0}}}
                                     ).naming
    aggs = [_agg(0, avg_clv=100), _agg(1, avg_clv=300), _agg(2, avg_clv=200)]
    names = name_segments(aggs, naming, THRESHOLD)
    assert {sid: n[0] for sid, n in names.items()} == {
        1: "High Value / High Risk (Established) #1", 2: "High Value / High Risk (Established) #2",
        0: "High Value / High Risk (Established) #3"}
    permuted = [dataclasses.replace(a, segment_id=(a.segment_id + 1) % 3) for a in aggs]
    pnames = name_segments(permuted, naming, THRESHOLD)
    for a, b in zip(aggs, permuted, strict=True):
        assert names[a.segment_id][0] == pnames[b.segment_id][0]


def test_names_follow_the_customers_when_cluster_ids_are_permuted(world):
    """Relabel the clusters: every customer keeps the same segment name."""
    frame, res, business = world["frame"], world["result"], world["business"]
    names = {p.segment_id: p.segment_name for p in res.profiles}
    original = [names[int(s)] for s in res.segment_ids]
    for perm in ([2, 0, 1], [1, 2, 0], [2, 1, 0]):
        perm = np.array(perm)
        ids = perm[res.segment_ids]
        profiles = profile_segments(frame, ids, res.business_profiles, business, world["features"],
                                    world["cfg"].naming, world["cfg"].priority, THRESHOLD, "customerID")
        pnames = {p.segment_id: p.segment_name for p in profiles}
        assert [pnames[int(s)] for s in ids] == original
        ranks = {p.segment_name: p.priority_rank for p in profiles}
        assert ranks == {p.segment_name: p.priority_rank for p in res.profiles}


# ------------------------------------------------------------------------------------------------ priority
def test_priority_score_is_the_documented_weighted_mean(world):
    res, prio = world["result"], world["cfg"].priority
    total_var = sum(p.total_value_at_risk for p in res.profiles)
    total_enb = sum(p.total_enb for p in res.profiles)
    w = prio.weights
    for p in res.profiles:
        expected = (w["value_at_risk_share"] * p.total_value_at_risk / total_var
                    + w["total_enb_share"] * p.total_enb / total_enb
                    + w["avg_churn_probability"] * p.avg_churn_probability
                    + w["intervention_rate"] * p.intervention_rate) / sum(w.values())
        assert p.priority_score == pytest.approx(expected) and 0.0 <= p.priority_score <= 1.0
    ranked = sorted(res.profiles, key=lambda p: p.priority_rank)
    assert [p.priority_rank for p in ranked] == [1, 2, 3]
    assert [p.priority_score for p in ranked] == sorted((p.priority_score for p in res.profiles), reverse=True)


def test_priority_weights_and_tiers_are_configurable():
    a = [_agg(0, total_var=100, total_enb=10, avg_prob=0.2, treated=0),
         _agg(1, total_var=300, total_enb=0, avg_prob=0.9, treated=100)]
    only_prob = load_segmentation_config(only(avg_churn_probability=1.0)).priority
    assert priority_scores(a, only_prob) == {0: pytest.approx(0.2), 1: pytest.approx(0.9)}
    only_var = load_segmentation_config(only(value_at_risk_share=3.0)).priority
    assert priority_scores(a, only_var) == {0: pytest.approx(0.25), 1: pytest.approx(0.75)}
    tiers = load_segmentation_config().priority
    assert [priority_tier(s, tiers) for s in (0.99, 0.30, 0.299, 0.15, 0.1499, 0.0)] == \
           ["HIGH", "HIGH", "MEDIUM", "MEDIUM", "LOW", "LOW"]


def test_enb_share_is_zero_when_portfolio_enb_is_not_positive():
    a = [_agg(0, total_var=100, total_enb=0.0), _agg(1, total_var=100, total_enb=-5.0)]
    only_enb = load_segmentation_config(only(total_enb_share=1.0)).priority
    assert priority_scores(a, only_enb) == {0: 0.0, 1: 0.0}
    only_var = load_segmentation_config(only(value_at_risk_share=1.0)).priority
    zero = [_agg(0, total_var=0.0), _agg(1, total_var=0.0)]
    assert priority_scores(zero, only_var) == {0: 0.0, 1: 0.0}


def test_priority_ties_are_ranked_deterministically(world):
    frame, res, business = world["frame"], world["result"], world["business"]
    prio = load_segmentation_config(only(intervention_rate=1.0)).priority
    profiles = profile_segments(frame, res.segment_ids, res.business_profiles, business, world["features"],
                                world["cfg"].naming, prio, THRESHOLD, "customerID")
    ranked = sorted(profiles, key=lambda p: p.priority_rank)
    assert ranked[0].intervention_rate == 1.0
    tied = [p for p in ranked if p.priority_score == 0.0]
    assert [p.total_value_at_risk for p in tied] == sorted((p.total_value_at_risk for p in tied), reverse=True)


# ------------------------------------------------------------------------------------------------- strategy
def test_strategy_is_the_phase4_recommendation_mix(world):
    res = world["result"]
    for prof in res.profiles:
        mine = [b for b, s in zip(res.business_profiles, res.segment_ids, strict=True) if s == prof.segment_id
                and b.intervention_decision == INTERVENE]
        mix = {}
        for b in mine:
            mix[b.recommended_action_id] = mix.get(b.recommended_action_id, 0) + 1
        assert prof.strategy.action_mix == dict(sorted(mix.items()))
        assert prof.strategy.intervention_count == len(mine)
        if mine:
            top = max(mix, key=lambda a: (mix[a], a == min(mix)))   # unique in this scenario
            assert prof.strategy.primary_action_id == top
            assert prof.strategy.primary_action_name == world["business"].actions[top].name
            assert "not a causal estimate" in prof.strategy.summary
        else:
            assert prof.strategy.primary_action_id == "no_action" and prof.strategy.action_mix == {}
            assert "No customer in this segment meets the Phase 4 intervention policy" in prof.strategy.summary


def test_strategy_changes_when_a_phase4_action_is_disabled_and_matches_phase4_choice(world, spec):
    disabled = load_business_config({"actions": {"discount_offer": {"enabled": False}}})
    engine = BusinessEngine(disabled, THRESHOLD)
    res = run_segmentation(world["frame"], world["probs"], engine, spec, world["cfg"], world["features"],
                           world["training"])
    seg = next(p for p in res.profiles if p.intervention_rate == 1.0)
    chosen = {b.recommended_action_id for b, s in zip(res.business_profiles, res.segment_ids, strict=True)
              if s == seg.segment_id}
    assert chosen == {seg.strategy.primary_action_id} and seg.strategy.primary_action_id != "discount_offer"
    # hand check of Phase 4's choice for a ~1440 CLV customer at p=0.40 (value at risk ~576):
    #   priority_support 576*0.18-40 = 63.7  >  loyalty_offer 576*0.15-25 = 61.4  > retention_email 576*0.05-2 = 26.8
    assert seg.strategy.primary_action_id == "priority_support"


def test_every_recommended_action_exists_in_the_phase4_configuration(world):
    known = set(world["business"].actions)
    for p in world["result"].profiles:
        assert p.strategy.primary_action_id in known and set(p.strategy.action_mix) <= known


# ------------------------------------------------------------------------------------------ assignments
def test_assignments_carry_id_segment_name_and_distance(world):
    res, frame = world["result"], world["frame"]
    names = {p.segment_id: p.segment_name for p in res.profiles}
    ids, dist = res.model.assign(frame)
    assert [a.customer_id for a in res.assignments] == frame["customerID"].tolist()
    assert [a.segment_id for a in res.assignments] == ids.tolist()
    assert [a.segment_name for a in res.assignments] == [names[i] for i in ids.tolist()]
    assert [a.distance_to_centroid for a in res.assignments] == pytest.approx(dist.tolist())
    assert set(res.assignments[0].to_dict()) == {"customer_id", "segment_id", "segment_name", "distance_to_centroid"}


def test_assign_new_customers_with_catalog_names(world):
    res = world["result"]
    names = {p.segment_id: p.segment_name for p in res.profiles}
    new = make_segment_frame(n_per_group=10, seed=77)
    out = assign_customers(res.model, names, new, "customerID")
    assert len(out) == 30 and {a.segment_name for a in out} == set(names.values())
    with pytest.raises(SegmentationInputError, match="Segment names are missing"):
        assign_customers(res.model, {0: "x"}, new)
    with pytest.raises(SegmentationInputError, match="id column"):
        assign_customers(res.model, names, new, "nope")
    assert assign_customers(res.model, names, new)[0].customer_id is None


def test_build_assignments_requires_a_name_for_every_segment(world):
    with pytest.raises(SegmentationConfigError, match="No profile"):
        build_assignments(["a"], np.array([5]), np.array([0.1]), world["result"].profiles)


# ---------------------------------------------------------------------------------------- input validation
def test_profile_inputs_are_validated(world):
    frame, res, business = world["frame"], world["result"], world["business"]
    args = (business, world["features"], world["cfg"].naming, world["cfg"].priority, THRESHOLD)
    with pytest.raises(SegmentationInputError, match="Got"):
        profile_segments(frame, res.segment_ids[:-1], res.business_profiles, *args)
    with pytest.raises(SegmentationInputError, match="empty"):
        profile_segments(frame.iloc[:0], res.segment_ids[:0], [], *args)
    reordered = frame.iloc[::-1]
    with pytest.raises(SegmentationInputError, match="not row-aligned"):
        profile_segments(reordered, res.segment_ids, res.business_profiles, *args, id_column="customerID")
    with pytest.raises(SegmentationInputError, match="id column"):
        profile_segments(frame, res.segment_ids, res.business_profiles, *args, id_column="nope")
    broken = {**world["features"], "roles": {**world["features"]["roles"], "tenure": "no_such_column"}}
    with pytest.raises(SegmentationInputError, match="no 'tenure' column"):
        profile_segments(frame, res.segment_ids, res.business_profiles, business, broken, world["cfg"].naming,
                         world["cfg"].priority, THRESHOLD)
    gap = np.where(res.segment_ids == 1, 2, res.segment_ids)
    with pytest.raises(SegmentationInputError, match="has no customers"):
        profile_segments(frame, gap, res.business_profiles, *args)


def test_probabilities_never_reach_the_clustering(world, spec):
    """Different churn probabilities change the business profile but cannot change the clusters."""
    frame, cfg = world["frame"], world["cfg"]
    a = world["result"]
    other = run_segmentation(frame, np.full(len(frame), 0.5), world["engine"], spec, cfg, world["features"],
                             world["training"])
    assert np.array_equal(a.segment_ids, other.segment_ids) and np.array_equal(a.model.centers, other.model.centers)
    assert [p.avg_churn_probability for p in a.profiles] != [p.avg_churn_probability for p in other.profiles]
    model, _ = fit_segmentation(frame, spec, cfg, world["features"], a.seed, 3)
    assert np.array_equal(model.centers, a.model.centers)


def _agg(i: int, *, avg_clv: float = 1000.0, avg_prob: float = 0.3, total_var: float = 100.0,
         total_enb: float = 10.0, treated: int = 10, count: int = 100, avg_tenure: float = 30.0) -> _Aggregate:
    return _Aggregate(i, count, avg_tenure, 50.0, 1000.0, avg_prob, avg_clv, avg_clv * count, total_var, total_enb,
                      total_enb / count, treated)
