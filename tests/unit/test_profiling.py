import numpy as np

from ml.pipelines.profiling import missing_mask, profile_dataset, quality_score


def test_blank_strings_count_as_missing(df, spec, quality_cfg):
    p = profile_dataset(df, spec, quality_cfg)
    assert p["missing_per_column"]["TotalCharges"] == int((df["tenure"] == 0).sum())
    assert p["rows"] == len(df) and p["columns"] == df.shape[1]


def test_profile_reports_target_and_imbalance(df, spec, quality_cfg):
    p = profile_dataset(df, spec, quality_cfg)
    assert sum(p["target_distribution"]["counts"].values()) == len(df)
    assert abs(p["imbalance"]["positive_rate"] - (df["Churn"] == "Yes").mean()) < 1e-9


def test_profile_detects_structure(df, spec, quality_cfg):
    df["const"] = 1
    df["allnull"] = np.nan
    p = profile_dataset(df, spec, quality_cfg)
    assert "const" in p["constant_columns"]
    assert "allnull" in p["all_null_columns"]


def test_id_like_detection(df, spec, quality_cfg):
    df["Ref"] = [f"R{i}" for i in range(len(df))]
    assert "Ref" in profile_dataset(df, spec, quality_cfg)["id_like_columns"]


def test_missing_mask_numeric_and_text():
    import pandas as pd
    assert missing_mask(pd.Series([1.0, np.nan])).tolist() == [False, True]
    assert missing_mask(pd.Series(["a", " ", None])).tolist() == [False, True, True]


def test_score_is_documented_formula_clean_data(df, spec, quality_cfg):
    df = df.copy()
    df.loc[df["tenure"] == 0, "TotalCharges"] = "0"
    q = quality_score(profile_dataset(df, spec, quality_cfg), False, quality_cfg)
    assert q["band"] == "Excellent" and q["score"] >= 99


def test_score_penalises_each_component(df, spec, quality_cfg):
    base = quality_score(profile_dataset(df, spec, quality_cfg), False, quality_cfg)["score"]
    d2 = df.copy()
    for c in ["Partner", "Dependents", "gender"]:
        d2.loc[d2.sample(frac=0.4, random_state=0).index, c] = np.nan
    q = quality_score(profile_dataset(d2, spec, quality_cfg), False, quality_cfg)
    assert q["components"]["missing"] > 0 and q["score"] < base


def test_score_imbalance_and_small_sample(spec, quality_cfg):
    from tests.conftest import make_churn_frame
    d = make_churn_frame(400)
    d["Churn"] = "No"
    d.loc[:7, "Churn"] = "Yes"  # 2% minority
    q = quality_score(profile_dataset(d, spec, quality_cfg), False, quality_cfg)
    assert q["components"]["imbalance"] > 0 and q["components"]["sample_size"] > 0
    assert abs(q["score"] - (100 - sum(q["components"].values()))) < 0.11


def test_rejected_dataset_has_no_score(df, spec, quality_cfg):
    q = quality_score(profile_dataset(df, spec, quality_cfg), True, quality_cfg)
    assert q == {"score": None, "band": "Rejected", "components": {}}


def test_band_boundaries(quality_cfg):
    base = {"rows": 5000, "numeric_columns": ["a"], "categorical_columns": ["b"],
            "constant_columns": [], "id_like_columns": [], "all_null_columns": [],
            "duplicate_rows": 0, "duplicate_ids": 0, "imbalance": {"minority_share": 0.3}}
    assert quality_score({**base, "overall_missing_fraction": 0.0}, False, quality_cfg)["band"] == "Excellent"
    assert quality_score({**base, "overall_missing_fraction": 0.1}, False, quality_cfg)["band"] == "Good"  # 100-15
    assert quality_score({**base, "overall_missing_fraction": 0.2, "duplicate_rows": 500},
                         False, quality_cfg)["band"] == "Needs Attention"  # 100-30-10=60 ... see below
