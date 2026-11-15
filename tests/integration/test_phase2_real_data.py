"""Phase 2 on the real IBM Telco CSV (reduced search for speed). Skipped when the file is missing."""
import json
from pathlib import Path

import pytest

from ml.pipelines.ingestion import dataset_version, load_csv
from ml.pipelines.optimization import run_optimization
from ml.pipelines.serialization import load_artifact
from tests.conftest import make_fast_opt_cfg

CSV = Path("ml/data/raw/telco_churn.csv")
pytestmark = [pytest.mark.integration,
              pytest.mark.skipif(not CSV.exists(), reason="run `make data` first")]


@pytest.fixture(scope="module")
def report(spec, quality_cfg, training_cfg, features_cfg, tmp_path_factory):
    cfg = make_fast_opt_cfg({"tuning": {"n_iter": {"logistic_regression": 6, "random_forest": 3, "xgboost": 6}}})
    return run_optimization(load_csv(CSV), spec, quality_cfg, training_cfg, features_cfg, cfg,
                            dataset_info={"version": dataset_version(CSV)},
                            artifact_dir=tmp_path_factory.mktemp("models"))


def test_real_data_final_metrics_are_plausible(report):
    f = report.final
    assert 0.78 < f.probability_metrics["roc_auc"] < 0.90
    assert f.probability_metrics["pr_auc"] > 0.55
    assert f.probability_metrics["brier"] < 0.17
    assert 0.2 < f.threshold < 0.7
    assert f.threshold_metrics["recall"] > 0.5 and f.threshold_metrics["f1"] > 0.55
    assert sum(report.split_sizes.values()) == 7043


def test_real_data_calibration_beats_or_matches_uncalibrated(report):
    c = report.decisions.calibration
    assert c.candidates[c.method]["brier"] <= c.candidates["none"]["brier"]


def test_real_data_artifact_loads_and_scores_raw_records(report):
    art = load_artifact(report.artifact.model)
    df = load_csv(CSV).head(25)
    p = art.predict_proba(df)
    assert p.shape == (25,) and ((p >= 0) & (p <= 1)).all()
    assert art.metadata["feature_count"] == 19      # Telco: 21 columns - customerID - Churn


def test_real_report_serialises(report):
    json.dumps(report.to_dict(), default=str)
