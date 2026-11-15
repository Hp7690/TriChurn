import numpy as np
import pandas as pd
import pytest
from sklearn.base import clone
from sklearn.linear_model import LogisticRegression

from ml.pipelines.feature_engineering import FEATURE_DOCS, FeatureEngineer
from ml.pipelines.preprocessing import (
    FrameCoercer,
    build_pipeline,
    plan_features,
    prepare_xy,
)
from tests.conftest import make_churn_frame


def _xy(df, spec, quality_cfg):
    plan = plan_features(df, spec, quality_cfg)
    X, y, ids = prepare_xy(df, spec, plan)
    return plan, X, y, ids


def test_plan_excludes_id_and_target(df, spec, quality_cfg):
    plan = plan_features(df, spec, quality_cfg)
    assert "customerID" not in plan.features and "Churn" not in plan.features
    assert plan.dropped["customerID"] == "id_column" and plan.dropped["Churn"] == "target"


def test_plan_drops_constant_allnull_idlike(df, spec, quality_cfg):
    df["c"], df["n"] = 1, np.nan
    df["ref"] = [f"R{i}" for i in range(len(df))]
    plan = plan_features(df, spec, quality_cfg)
    assert plan.dropped["c"] == "constant" and plan.dropped["n"] == "all_null"
    assert plan.dropped["ref"] == "id_like"


def test_prepare_xy_excludes_unlabeled_rows(df, spec, quality_cfg):
    df.loc[:4, "Churn"] = np.nan
    _, X, y, ids = _xy(df, spec, quality_cfg)
    assert len(X) == len(y) == len(ids) == len(df) - 5
    assert set(y.unique()) == {0, 1}
    assert y.mean() == pytest.approx((df["Churn"].dropna() == "Yes").mean())


def test_coercer_handles_blank_totalcharges_and_garbage():
    c = FrameCoercer(["a"], ["b"])
    out = c.transform(pd.DataFrame({"a": [" ", "3.5", "x", "inf"], "b": [" y ", "", None, 3]}))
    assert out["a"].isna().tolist() == [True, False, True, True]
    assert out["b"].tolist()[0] == "y" and pd.isna(out["b"].iloc[1]) and out["b"].iloc[3] == "3"


def test_coercer_tolerates_missing_columns_at_inference():
    out = FrameCoercer(["a"], ["b"]).transform(pd.DataFrame({"zzz": [1]}))
    assert out["a"].isna().all() and out["b"].isna().all()


# ---- feature engineering -----------------------------------------------
def test_feature_engineer_creates_documented_features(df, spec, quality_cfg, features_cfg):
    _, X, _, _ = _xy(df, spec, quality_cfg)
    Xc = FrameCoercer(spec.numerical, spec.categorical).transform(X)
    fe = FeatureEngineer(features_cfg).fit(Xc)
    out = fe.transform(Xc)
    assert set(fe.created_) <= set(FEATURE_DOCS) and "support_calls_per_month" in fe.skipped_
    assert set(fe.created_) <= set(out.columns)
    assert out["contract_risk"].isin([0, 1, 2]).all()
    assert (out["service_count"] >= out["protective_service_count"]).all()
    assert out["tenure_group"].isin(["0-12m", "13-24m", "25-48m", "49m+"]).all()
    assert out["monthly_vs_avg_charge_delta"].notna().all()


def test_feature_engineer_never_touches_target_and_is_deterministic(df, spec, quality_cfg, features_cfg):
    plan, X, y, _ = _xy(df, spec, quality_cfg)
    Xc = FrameCoercer(spec.numerical, spec.categorical).transform(X)
    a = FeatureEngineer(features_cfg).fit(Xc).transform(Xc)
    b = FeatureEngineer(features_cfg).fit(Xc).transform(Xc)
    pd.testing.assert_frame_equal(a, b)
    assert "Churn" not in a.columns
    # engineered columns must not be a (near) copy of the label
    for col in set(a.columns) - set(Xc.columns):
        if pd.api.types.is_numeric_dtype(a[col]):
            assert abs(np.corrcoef(a[col].fillna(0), y)[0, 1]) < 0.9


def test_feature_engineer_skips_missing_inputs_instead_of_faking(features_cfg):
    X = pd.DataFrame({"tenure": [1, 20, 40], "other": [1, 2, 3]})
    fe = FeatureEngineer(features_cfg).fit(X)
    assert fe.created_ == ["tenure_group"]
    assert "contract_risk" in fe.skipped_ and "service_count" in fe.skipped_
    assert list(fe.transform(X).columns) == ["tenure", "other", "tenure_group"]


def test_support_calls_feature_when_column_exists(features_cfg):
    cfg = {**features_cfg, "roles": {**features_cfg["roles"], "support_calls": "calls"}}
    X = pd.DataFrame({"tenure": [10, 0, 5], "calls": [5, 2, 0]})
    out = FeatureEngineer(cfg).fit(X).transform(X)
    assert out["support_calls_per_month"].tolist() == [0.5, 2.0, 0.0]


def test_charge_band_edges_learned_from_fit_data_only(features_cfg):
    low = pd.DataFrame({"MonthlyCharges": np.linspace(10, 20, 100)})
    high = pd.DataFrame({"MonthlyCharges": np.linspace(100, 200, 100)})
    fe = FeatureEngineer(features_cfg).fit(low)
    assert max(fe.edges_) <= 20  # unaffected by the 'future' data
    assert (fe.transform(high)["monthly_charge_band"] == "Q4").all()


def test_feature_engineer_is_clonable_and_picklable(features_cfg):
    import pickle
    fe = FeatureEngineer(features_cfg)
    clone(fe)
    pickle.dumps(fe)


# ---- full pipeline ------------------------------------------------------
def test_pipeline_predicts_on_raw_records_and_unseen_categories(df, spec, quality_cfg, features_cfg):
    plan, X, y, _ = _xy(df, spec, quality_cfg)
    pipe = build_pipeline(plan, LogisticRegression(max_iter=500), features_cfg).fit(X, y)
    new = X.head(3).copy()
    new["Contract"] = ["Brand New Plan", "Month-to-month", None]  # unseen + missing
    new["PaymentMethod"] = "Crypto"
    new["TotalCharges"] = ["", "abc", "10"]
    p = pipe.predict_proba(new)[:, 1]
    assert p.shape == (3,) and np.isfinite(p).all() and ((p >= 0) & (p <= 1)).all()


def test_pipeline_handles_missing_values_everywhere(spec, quality_cfg, features_cfg):
    d = make_churn_frame(800, seed=3)
    for c in ["Contract", "tenure", "MonthlyCharges", "TechSupport"]:
        d.loc[d.sample(frac=0.15, random_state=4).index, c] = np.nan
    plan, X, y, _ = _xy(d, spec, quality_cfg)
    pipe = build_pipeline(plan, LogisticRegression(max_iter=500), features_cfg).fit(X, y)
    assert np.isfinite(pipe.predict_proba(X)[:, 1]).all()


def test_pipeline_accepts_a_single_record(df, spec, quality_cfg, features_cfg):
    plan, X, y, _ = _xy(df, spec, quality_cfg)
    pipe = build_pipeline(plan, LogisticRegression(max_iter=500), features_cfg).fit(X, y)
    assert pipe.predict_proba(X.iloc[[0]]).shape == (1, 2)
