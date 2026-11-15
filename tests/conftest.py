"""Shared fixtures. The synthetic generator is for TESTS ONLY - no reported metric uses it."""
from __future__ import annotations

import numpy as np
import pandas as pd
import pytest

from ml.config import deep_merge, load_config
from ml.pipelines.ingestion import DatasetSpec


def make_churn_frame(n: int = 1200, seed: int = 0, churn_target_rate: float = 0.27,
                     with_missing: bool = True) -> pd.DataFrame:
    """Telco-shaped synthetic data with real (non-trivial) signal and some noise."""
    rng = np.random.default_rng(seed)
    contract = rng.choice(["Month-to-month", "One year", "Two year"], n, p=[0.55, 0.25, 0.20])
    tenure = rng.integers(0, 73, n)
    monthly = np.round(rng.uniform(18, 118, n), 2)
    pay = rng.choice(["Electronic check", "Mailed check", "Bank transfer (automatic)",
                      "Credit card (automatic)"], n)
    yn = lambda p: rng.choice(["Yes", "No"], n, p=[p, 1 - p])  # noqa: E731
    tech, sec = yn(0.3), yn(0.3)
    logit = (
        -1.2
        + 1.3 * (contract == "Month-to-month")
        - 0.9 * (contract == "Two year")
        - 0.035 * tenure
        + 0.012 * (monthly - 65)
        + 0.5 * (pay == "Electronic check")
        - 0.4 * (tech == "Yes")
        + rng.normal(0, 0.8, n)
    )
    logit += np.log(churn_target_rate / (1 - churn_target_rate)) - np.log(0.27 / 0.73)
    churn = rng.random(n) < 1 / (1 + np.exp(-logit))
    total = np.round(monthly * np.maximum(tenure, 1) + rng.normal(0, 20, n), 2)
    df = pd.DataFrame({
        "customerID": [f"C{i:05d}" for i in range(n)],
        "gender": rng.choice(["Male", "Female"], n),
        "SeniorCitizen": rng.choice([0, 1], n, p=[0.84, 0.16]),
        "Partner": yn(0.5), "Dependents": yn(0.3),
        "tenure": tenure,
        "PhoneService": yn(0.9), "MultipleLines": rng.choice(["Yes", "No", "No phone service"], n),
        "InternetService": rng.choice(["DSL", "Fiber optic", "No"], n),
        "OnlineSecurity": sec, "OnlineBackup": yn(0.35), "DeviceProtection": yn(0.35),
        "TechSupport": tech, "StreamingTV": yn(0.4), "StreamingMovies": yn(0.4),
        "Contract": contract, "PaperlessBilling": yn(0.6), "PaymentMethod": pay,
        "MonthlyCharges": monthly, "TotalCharges": total.astype(str),
        "Churn": np.where(churn, "Yes", "No"),
    })
    if with_missing:  # Telco-style blank TotalCharges for brand-new customers
        df.loc[df["tenure"] == 0, "TotalCharges"] = " "
    return df


SERVICE_COLUMNS = ["PhoneService", "MultipleLines", "OnlineSecurity", "OnlineBackup", "DeviceProtection",
                   "TechSupport", "StreamingTV", "StreamingMovies"]
# (tenure, monthly charge, number of services, contract) of three well-separated customer archetypes
ARCHETYPES = [(5, 30.0, 1, "Month-to-month"), (40, 60.0, 4, "One year"), (68, 100.0, 8, "Two year")]


def make_segment_frame(n_per_group: int = 120, seed: int = 0, blank_total_every: int = 40) -> pd.DataFrame:
    """Controlled customers (TESTS ONLY): three clearly separated archetypes + a random Churn column the clustering
    must ignore. ``group`` is the ground-truth archetype. Every ``blank_total_every``-th TotalCharges is blank."""
    rng = np.random.default_rng(seed)
    rows = []
    for g, (ten, mon, n_services, contract) in enumerate(ARCHETYPES):
        for i in range(n_per_group):
            tenure = max(1, int(round(ten + rng.normal(0, 1.5))))
            monthly = round(mon + rng.normal(0, 2.0), 2)
            row = {"customerID": f"G{g}-{i:04d}", "gender": "Female", "SeniorCitizen": 0, "Partner": "No",
                   "Dependents": "No", "tenure": tenure, "InternetService": "DSL", "Contract": contract,
                   "PaperlessBilling": "Yes", "PaymentMethod": "Mailed check", "MonthlyCharges": monthly,
                   "TotalCharges": round(tenure * monthly, 2), "Churn": rng.choice(["Yes", "No"]), "group": g}
            for j, col in enumerate(SERVICE_COLUMNS):
                row[col] = "Yes" if j < n_services else "No"
            rows.append(row)
    frame = pd.DataFrame(rows).sample(frac=1.0, random_state=seed).reset_index(drop=True)
    if blank_total_every:
        frame["TotalCharges"] = frame["TotalCharges"].astype(object)
        frame.loc[frame.index[::blank_total_every], "TotalCharges"] = " "      # as in the real Telco CSV
    return frame


def make_fast_opt_cfg(overrides: dict | None = None) -> dict:
    """Phase 2 config shrunk for tests (tiny search, 3 folds, small ensembles). Policy keys are unchanged."""
    fast = {
        "tuning": {
            "cv": {"n_splits": 3},
            "n_iter": {"logistic_regression": 4, "random_forest": 3, "xgboost": 3},
            "spaces": {"random_forest": {"n_estimators": [30, 50]}, "xgboost": {"n_estimators": [30, 60]}},
        },
        "calibration": {"cv_folds": 3},
    }
    return deep_merge(deep_merge(load_config("optimization"), fast), overrides or {})


@pytest.fixture(scope="session")
def optimization_cfg():
    return load_config("optimization")


@pytest.fixture(scope="session")
def fast_opt_cfg():
    return make_fast_opt_cfg()


@pytest.fixture(scope="session")
def quality_cfg():
    return load_config("quality")


@pytest.fixture(scope="session")
def training_cfg():
    return load_config("training")


@pytest.fixture(scope="session")
def features_cfg():
    return load_config("features")


@pytest.fixture(scope="session")
def spec():
    return DatasetSpec.from_yaml("configs/datasets/telco.yaml")


@pytest.fixture()
def df():
    return make_churn_frame()
