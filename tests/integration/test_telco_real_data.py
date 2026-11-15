"""Trains on the real IBM Telco CSV. Skipped when the file has not been downloaded."""
import json
from pathlib import Path

import pytest

from ml.pipelines.ingestion import dataset_version, load_csv
from ml.pipelines.training import MODEL_NAMES, run_training

CSV = Path("ml/data/raw/telco_churn.csv")
pytestmark = [pytest.mark.integration,
              pytest.mark.skipif(not CSV.exists(), reason="run `make data` first")]


@pytest.fixture(scope="module")
def report(spec, quality_cfg, training_cfg, features_cfg):
    cfg = {**training_cfg, "cv": {"n_splits": 3}}
    return run_training(load_csv(CSV), spec, quality_cfg, cfg, features_cfg,
                        dataset_info={"version": dataset_version(CSV)})


def test_real_dataset_profile(report):
    p = report.profile
    assert (p["rows"], p["columns"]) == (7043, 21)
    assert p["target_distribution"]["counts"] == {"No": 5174, "Yes": 1869}
    assert p["missing_per_column"]["TotalCharges"] == 11
    assert p["duplicate_ids"] == 0
    assert report.quality["band"] == "Excellent"


def test_real_data_models_beat_chance_and_are_plausible(report):
    for r in report.results:
        assert 0.78 < r.validation["roc_auc"] < 0.90, (r.name, r.validation["roc_auc"])
        assert r.validation["pr_auc"] > 0.5
    assert {r.name for r in report.results} == set(MODEL_NAMES)


def test_real_report_serialises(report):
    json.dumps(report.to_dict())
