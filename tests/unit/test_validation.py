import numpy as np
import pandas as pd
import pytest

from ml.errors import IngestionError, ValidationError
from ml.pipelines.ingestion import load_csv
from ml.pipelines.preprocessing import plan_features
from ml.pipelines.training import split_raw
from ml.pipelines.validation import validate_dataset, validate_training_data
from tests.conftest import make_churn_frame


def codes(rep, severity="error"):
    return {i.code for i in rep.issues if i.severity == severity}


def train_validation(df, spec, quality_cfg):
    """TRAINING validation exactly as run_training does it: split -> train-only plan -> screen."""
    train = split_raw(df, spec, 0.15, 0.15, 42).train
    return validate_training_data(train, spec, quality_cfg, plan_features(train, spec, quality_cfg))


def test_valid_dataset_passes(df, spec, quality_cfg):
    rep = validate_dataset(df, spec, quality_cfg)
    assert rep.ok, rep.errors
    assert "MISSING_VALUES" in codes(rep, "warning")  # blank TotalCharges surfaced, not silent


def test_empty_dataframe(spec, quality_cfg):
    rep = validate_dataset(pd.DataFrame(), spec, quality_cfg)
    assert codes(rep) == {"EMPTY_DATASET"}


def test_missing_target_column(df, spec, quality_cfg):
    rep = validate_dataset(df.drop(columns=["Churn"]), spec, quality_cfg)
    assert codes(rep) == {"MISSING_TARGET"}


def test_all_null_target(df, spec, quality_cfg):
    df["Churn"] = np.nan
    assert codes(validate_dataset(df, spec, quality_cfg)) == {"NULL_TARGET"}


def test_one_class_target(df, spec, quality_cfg):
    df["Churn"] = "No"
    assert "ONE_CLASS_TARGET" in codes(validate_dataset(df, spec, quality_cfg))


def test_wrong_positive_class_is_reported_as_one_class(df, spec, quality_cfg):
    spec2 = type(spec)(**{**spec.to_dict(), "positive_class": "Maybe"})
    assert "ONE_CLASS_TARGET" in codes(validate_dataset(df, spec2, quality_cfg))


def test_partial_null_target_is_warning_and_rows_excluded(df, spec, quality_cfg):
    df.loc[:9, "Churn"] = np.nan
    rep = validate_dataset(df, spec, quality_cfg)
    assert rep.ok and "TARGET_PARTIAL_NULL" in codes(rep, "warning")


def test_duplicate_customer_ids_rejected(df, spec, quality_cfg):
    df.loc[5, "customerID"] = df.loc[4, "customerID"]
    assert "DUPLICATE_IDS" in codes(validate_dataset(df, spec, quality_cfg))


def test_duplicate_rows_warn_only(df, spec, quality_cfg):
    dup = pd.concat([df, df.iloc[[0]]], ignore_index=True)
    dup.loc[len(dup) - 1, "customerID"] = "NEW-ID"  # unique id but identical otherwise? -> differs
    rep = validate_dataset(pd.concat([df, df.iloc[:3]]).drop(columns=["customerID"]),
                           type(spec)(**{**spec.to_dict(), "id_column": None}), quality_cfg)
    assert rep.ok and "DUPLICATE_ROWS" in codes(rep, "warning")


def test_too_few_rows(spec, quality_cfg):
    rep = validate_dataset(make_churn_frame(40), spec, quality_cfg)
    assert "TOO_FEW_ROWS" in codes(rep)


def test_extreme_class_imbalance_rejected_when_minority_tiny(spec, quality_cfg):
    d = make_churn_frame(1000)
    d["Churn"] = "No"
    d.loc[:4, "Churn"] = "Yes"  # 5 positives
    assert "TOO_FEW_MINORITY_SAMPLES" in codes(validate_dataset(d, spec, quality_cfg))


def test_all_null_column_warns_and_is_not_fatal(df, spec, quality_cfg):
    df["Empty"] = np.nan
    rep = validate_dataset(df, spec, quality_cfg)
    assert rep.ok and "ALL_NULL_COLUMN" in codes(rep, "warning")


def test_invalid_numeric_values(df, spec, quality_cfg):
    df["MonthlyCharges"] = df["MonthlyCharges"].astype(str)
    df.loc[df.index[: len(df) // 2], "MonthlyCharges"] = "abc"
    assert "INVALID_NUMERIC_VALUES" in codes(validate_dataset(df, spec, quality_cfg))


def test_a_few_invalid_numeric_values_only_warn(df, spec, quality_cfg):
    df["MonthlyCharges"] = df["MonthlyCharges"].astype(str)
    df.loc[[1, 2], "MonthlyCharges"] = "oops"
    rep = validate_dataset(df, spec, quality_cfg)
    assert rep.ok and "INVALID_NUMERIC_VALUES" in codes(rep, "warning")


def test_extremely_large_values_rejected(df, spec, quality_cfg):
    df.loc[3, "MonthlyCharges"] = 1e15
    assert "EXTREME_VALUES" in codes(validate_dataset(df, spec, quality_cfg))


def test_excessive_missingness_rejected(df, spec, quality_cfg):
    for c in spec.categorical:
        df.loc[df.sample(frac=0.8, random_state=1).index, c] = np.nan
    for c in spec.numerical:
        df.loc[df.sample(frac=0.8, random_state=2).index, c] = np.nan
    assert "EXCESSIVE_MISSINGNESS" in codes(validate_dataset(df, spec, quality_cfg))


def test_datetime_column_rejected(df, spec, quality_cfg):
    df["signup"] = pd.Timestamp("2024-01-01")
    spec2 = type(spec)(**{**spec.to_dict()})
    assert "UNSUPPORTED_TYPE" in codes(validate_dataset(df, spec2, quality_cfg))


def test_nested_values_rejected(df, spec, quality_cfg):
    df["blob"] = [[1, 2]] * len(df)
    assert "UNSUPPORTED_TYPE" in codes(validate_dataset(df, spec, quality_cfg))


def test_leakage_perfect_copy_of_target_rejected(df, spec, quality_cfg):
    df["Outcome"] = np.where(df["Churn"] == "Yes", "lost", "kept")
    rep = train_validation(df, spec, quality_cfg)
    assert "POSSIBLE_TARGET_LEAKAGE" in codes(rep)
    assert any(i.column == "Outcome" for i in rep.errors)


def test_leakage_by_column_name(df, spec, quality_cfg):
    df["ChurnScore"] = np.random.default_rng(0).random(len(df))
    assert any(i.column == "ChurnScore" for i in train_validation(df, spec, quality_cfg).errors)


def test_leakage_numeric_proxy_of_target(df, spec, quality_cfg):
    df["risk_index"] = (df["Churn"] == "Yes").astype(float) * 10 + np.random.default_rng(0).random(len(df)) * 0.01
    assert any(i.column == "risk_index" for i in train_validation(df, spec, quality_cfg).errors)


def test_legitimate_features_not_flagged_as_leakage(df, spec, quality_cfg):
    assert "POSSIBLE_TARGET_LEAKAGE" not in codes(train_validation(df, spec, quality_cfg))


def test_dataset_validation_is_structural_and_runs_no_target_informed_screen(
        df, spec, quality_cfg, monkeypatch):
    """validate_dataset (raw/full data) must not call the leakage screen nor flag leakage."""
    import ml.pipelines.validation as v

    def boom(*a, **k):
        raise AssertionError("target-informed leakage screen ran during structural validation")

    monkeypatch.setattr(v, "find_leakage_suspects", boom)
    df["Outcome"] = np.where(df["Churn"] == "Yes", "lost", "kept")  # blatant leak
    rep = validate_dataset(df, spec, quality_cfg)
    assert rep.ok and "POSSIBLE_TARGET_LEAKAGE" not in codes(rep)


def test_training_validation_reports_train_based_feature_drops(df, spec, quality_cfg):
    df["flat"] = 1
    rep = train_validation(df, spec, quality_cfg)
    assert any(i.code == "FEATURE_DROPPED" and i.column == "flat" for i in rep.warnings)


def test_raise_if_invalid_gives_friendly_message(df, spec, quality_cfg):
    df["Churn"] = "No"
    with pytest.raises(ValidationError, match="ONE_CLASS_TARGET"):
        validate_dataset(df, spec, quality_cfg).raise_if_invalid()


# ---- ingestion ---------------------------------------------------------
def test_load_csv_rejects_wrong_extension(tmp_path):
    p = tmp_path / "x.xlsx"
    p.write_text("a,b\n1,2\n")
    with pytest.raises(IngestionError, match="Unsupported file type"):
        load_csv(p)


def test_load_csv_rejects_oversized(tmp_path):
    p = tmp_path / "big.csv"
    p.write_text("a\n" + "1\n" * 200_000)
    with pytest.raises(IngestionError, match="limit"):
        load_csv(p, max_file_mb=0.1)


def test_load_csv_empty_file(tmp_path):
    p = tmp_path / "e.csv"
    p.write_text("")
    with pytest.raises(IngestionError, match="empty"):
        load_csv(p)


def test_load_csv_header_only(tmp_path):
    p = tmp_path / "h.csv"
    p.write_text("a,b\n")
    with pytest.raises(IngestionError, match="no data rows"):
        load_csv(p)
