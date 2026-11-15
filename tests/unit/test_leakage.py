"""Data-leakage tests: nothing that learns from data may see validation/test rows."""
import inspect

import numpy as np
import pytest
from sklearn.base import BaseEstimator, TransformerMixin, clone
from sklearn.linear_model import LogisticRegression
from sklearn.model_selection import cross_validate

from ml.pipelines.evaluation import cv_splitter
from ml.pipelines.preprocessing import build_pipeline, plan_features, prepare_xy
from ml.pipelines.training import split_data, train_models


class FitSpy(BaseEstimator, TransformerMixin):
    """Records the index of every frame it is fitted on (class-level so clones share it)."""
    seen: list = []

    def fit(self, X, y=None):
        FitSpy.seen.append(frozenset(X.index))
        return self

    def transform(self, X):
        return X


def assert_fits_only_on_train_folds(seen_sets, folds, X):
    for seen, (tr, va) in zip(seen_sets, folds, strict=True):
        assert seen == frozenset(X.index[tr])
        assert not (seen & set(X.index[va])), "validation rows leaked into fit"


def _prep(df, spec, quality_cfg):
    plan = plan_features(df, spec, quality_cfg)
    X, y, _ = prepare_xy(df, spec, plan)
    return plan, X, y


def test_split_is_disjoint_stratified_and_complete(df, spec, quality_cfg):
    _, X, y = _prep(df, spec, quality_cfg)
    s = split_data(X, y, 0.15, 0.15, 42)
    parts = [set(s.X_train.index), set(s.X_val.index), set(s.X_test.index)]
    assert not (parts[0] & parts[1]) and not (parts[0] & parts[2]) and not (parts[1] & parts[2])
    assert sum(map(len, parts)) == len(X)
    for yy in (s.y_train, s.y_val, s.y_test):
        assert abs(yy.mean() - y.mean()) < 0.02
    assert abs(len(s.X_test) / len(X) - 0.15) < 0.01 and abs(len(s.X_val) / len(X) - 0.15) < 0.01


def test_every_cv_fold_fits_transformers_on_its_training_rows_only(df, spec, quality_cfg, features_cfg):
    plan, X, y = _prep(df, spec, quality_cfg)
    pipe = build_pipeline(plan, LogisticRegression(max_iter=300), features_cfg)
    pipe.steps.insert(1, ("spy", FitSpy()))
    FitSpy.seen = []
    folds = list(cv_splitter(5, 0).split(X, y))
    cross_validate(clone(pipe), X, y, cv=folds, scoring="roc_auc", n_jobs=1)
    assert len(FitSpy.seen) == 5
    assert_fits_only_on_train_folds(FitSpy.seen, folds, X)


def test_scaler_and_imputer_statistics_come_from_train_only(spec, quality_cfg, features_cfg):
    from tests.conftest import make_churn_frame
    d = make_churn_frame(1500, seed=7, with_missing=False)
    d.loc[d.sample(frac=0.1, random_state=1).index, "MonthlyCharges"] = np.nan
    plan, X, y = _prep(d, spec, quality_cfg)
    s = split_data(X, y, 0.15, 0.15, 42)
    pipe = build_pipeline(plan, LogisticRegression(max_iter=300), features_cfg).fit(s.X_train, s.y_train)

    pre = pipe.named_steps["preprocess"]
    num_cols = pre.transformers_[0][2]
    num_pipe = pre.named_transformers_["num"]
    engineered = pipe[:2].transform
    train_frame, full_frame = engineered(s.X_train)[num_cols], engineered(X)[num_cols]

    # imputer medians == TRAIN medians (not full-data medians)
    np.testing.assert_allclose(num_pipe["impute"].statistics_, train_frame.median().to_numpy())
    assert not np.allclose(num_pipe["impute"].statistics_, full_frame.median().to_numpy(), rtol=0, atol=1e-12)
    # scaler mean == mean of imputed TRAIN data, and differs from full-data mean
    train_imputed = num_pipe["impute"].transform(train_frame)
    np.testing.assert_allclose(num_pipe["scale"].mean_, train_imputed.mean(axis=0))
    assert not np.allclose(num_pipe["scale"].mean_, full_frame.fillna(full_frame.median()).mean().to_numpy(),
                           rtol=0, atol=1e-12)


def test_encoder_vocabulary_comes_from_train_only(df, spec, quality_cfg, features_cfg):
    plan, X, y = _prep(df, spec, quality_cfg)
    X_train = X.copy()
    X_train["PaymentMethod"] = X_train["PaymentMethod"].replace("Mailed check", "Electronic check")
    pipe = build_pipeline(plan, LogisticRegression(max_iter=300), features_cfg).fit(X_train, y)
    enc = pipe.named_steps["preprocess"].named_transformers_["cat"]["onehot"]
    vocab = set(np.concatenate(enc.categories_))
    assert "Mailed check" not in vocab
    pipe.predict_proba(X.head(20))  # ...and unseen category at inference must not crash


def test_training_function_has_no_access_to_the_test_split():
    params = set(inspect.signature(train_models).parameters)
    assert not {p for p in params if "test" in p}, "train_models must not receive test data"


def test_leaky_target_derived_feature_is_blocked_before_training(
        df, spec, quality_cfg, training_cfg, features_cfg):
    # Leakage is now screened on the TRAIN split (after the split), so real configs are required.
    from ml.errors import ValidationError
    from ml.pipelines.training import run_training
    df["retained_flag"] = np.where(df["Churn"] == "Yes", "no", "yes")
    try:
        run_training(df, spec, quality_cfg, training_cfg, features_cfg)
    except ValidationError as e:
        assert "POSSIBLE_TARGET_LEAKAGE" in str(e)
    else:
        raise AssertionError("leaky dataset was not rejected")


def test_negative_control_the_spy_check_detects_a_leaky_procedure(df, spec, quality_cfg):
    """If transformers were fitted on ALL rows before CV, the check above must fail."""
    _, X, y = _prep(df, spec, quality_cfg)
    folds = list(cv_splitter(5, 0).split(X, y))
    leaky_seen = [frozenset(X.index)] * 5  # what a pre-CV fit_transform(X) would look like
    with pytest.raises(AssertionError):
        assert_fits_only_on_train_folds(leaky_seen, folds, X)
