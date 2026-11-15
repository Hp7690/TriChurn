"""REAL integration: the production ``Phase15Adapter`` against the existing Phase 1-5 code and locked artifacts.

Skipped ONLY when the existing project is not present (a standalone overlay run): the skip reason says so. In your
merged project these tests must run and pass. Expected values are obtained by calling Phase 2-5 DIRECTLY, then
compared with what the API returns.
"""
from __future__ import annotations

import hashlib
import importlib.util
import shutil
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from app.core.config import LOCKED_PHASE2_SHA256, Settings
from app.main import create_app
from tests.api.conftest import assert_error

SETTINGS = Settings(environment="development")
ROOT = SETTINGS.project_root
MODEL = SETTINGS.resolve(SETTINGS.phase2_model_path)
SEGMENTATION = SETTINGS.resolve(SETTINGS.phase5_model_path)
CSV = SETTINGS.resolve(SETTINGS.dataset_csv_path)
SPEC = SETTINGS.resolve(SETTINGS.dataset_spec_path)

HAVE_PROJECT = (importlib.util.find_spec("ml") is not None and MODEL.is_file() and SEGMENTATION.is_file()
                and CSV.is_file() and SPEC.is_file())
pytestmark = pytest.mark.skipif(
    not HAVE_PROJECT, reason="existing Phase 1-5 project (ml package, locked artifacts, dataset) not present")

FEATURES = ["SeniorCitizen", "tenure", "MonthlyCharges", "TotalCharges", "gender", "Partner", "Dependents",
            "PhoneService", "MultipleLines", "InternetService", "OnlineSecurity", "OnlineBackup", "DeviceProtection",
            "TechSupport", "StreamingTV", "StreamingMovies", "Contract", "PaperlessBilling", "PaymentMethod"]
TOL = 1e-9


def _artifact_fingerprint() -> dict[str, str]:
    files = [p for p in (ROOT / "models").glob("*") if p.is_file()]
    return {p.name: hashlib.sha256(p.read_bytes()).hexdigest() for p in files}


@pytest.fixture(scope="module", autouse=True)
def artifacts_are_never_modified():
    before = _artifact_fingerprint()
    yield
    assert _artifact_fingerprint() == before, "the API layer modified a file in models/"


@pytest.fixture(scope="module")
def frame():
    from ml.pipelines.ingestion import load_csv
    return load_csv(CSV)


@pytest.fixture(scope="module")
def customers(frame):
    """25 spread rows + 3 brand-new customers (tenure 0, blank TotalCharges)."""
    idx = list(range(0, len(frame), 280))[:25]
    idx += list(frame.index[frame["tenure"].astype(str) == "0"][:3])
    return [int(i) for i in idx]


def payload_for(frame, i: int) -> dict:
    row = frame.iloc[i]
    total = str(row["TotalCharges"]).strip()
    feats = {c: row[c] for c in FEATURES}
    feats.update(SeniorCitizen=int(row["SeniorCitizen"]), tenure=int(row["tenure"]),
                 MonthlyCharges=float(row["MonthlyCharges"]), TotalCharges=float(total) if total else None)
    return {"customer_id": str(row["customerID"]), "features": feats}


@pytest.fixture(scope="module")
def client():
    c = TestClient(create_app(settings=SETTINGS))
    assert c.get("/api/v1/readiness").status_code == 200       # loads Phase 2-5 once (lazy, thread-safe)
    return c


@pytest.fixture(scope="module")
def direct():
    """The existing Phase 2-5 objects, built the way the project's own scripts build them."""
    from ml.business import BusinessEngine, load_business_config
    from ml.explainability import ChurnShapExplainer, load_train_background, load_verified_artifact
    from ml.pipelines.ingestion import DatasetSpec
    from ml.segmentation import load_verified_segmentation_artifact
    spec = DatasetSpec.from_yaml(SPEC)
    churn = load_verified_artifact(MODEL)
    cfg = load_business_config()
    return {"churn": churn, "cfg": cfg, "engine": BusinessEngine(cfg, churn.artifact.threshold),
            "explainer": ChurnShapExplainer(churn, load_train_background(CSV, spec, churn)),
            "seg": load_verified_segmentation_artifact(SEGMENTATION)}


# ---------------------------------------------------------------------------------------------- readiness
def test_readiness_reports_the_locked_artifacts(client):
    body = client.get("/api/v1/readiness").json()
    assert body["ready"] is True
    assert {c["name"]: c["status"] for c in body["checks"]} == {
        "phase1_5_modules": "ok", "phase2_model": "ok", "feature_schema": "ok", "business_config": "ok",
        "business_engine": "ok", "explainability": "ok", "segmentation": "ok"}
    d = body["details"]
    assert d["phase2_sha256"] == LOCKED_PHASE2_SHA256 and d["phase2_sha256_pinned"] is True
    assert d["decision_threshold"] == 0.34 and d["model_version"] == "2.0.0"
    assert d["segmentation_k"] == 3 and d["phase5_sha256"] == hashlib.sha256(SEGMENTATION.read_bytes()).hexdigest()


# --------------------------------------------------------------------------------- API == direct Phase 2-5
def test_predict_equals_the_locked_phase2_model(client, direct, frame, customers):
    from ml.business import assign_risk_band
    art = direct["churn"].artifact
    for i in customers:
        r = client.post("/api/v1/predict", json=payload_for(frame, i))
        assert r.status_code == 200, r.text
        b, p = r.json(), float(art.predict_proba(frame.iloc[[i]])[0])
        assert b["churn_probability"] == pytest.approx(p, abs=TOL)
        assert b["decision_threshold"] == art.threshold == 0.34 and b["predicted_churn"] == (p >= 0.34)
        assert b["risk_band"] == assign_risk_band(p, direct["cfg"].risk_bands)
        assert (b["model_name"], b["model_version"]) == ("logistic_regression", "2.0.0")


def test_explain_equals_phase3_shap(client, direct, frame, customers):
    for i in customers:
        r = client.post("/api/v1/explain", json=payload_for(frame, i))
        assert r.status_code == 200, r.text
        b, expected = r.json(), direct["explainer"].explain(frame.iloc[[i]]).to_dict()
        assert len(b["features"]) == len(expected["features"]) == 26                  # 58 encoded -> 26 source
        assert b["reconstruction_error"] <= 1e-6 and b["output_space"] == "log_odds"
        assert b["base_value"] == pytest.approx(expected["base_value"], abs=TOL)
        assert [f["source_feature"] for f in b["features"]] == [f["source_feature"] for f in expected["features"]]
        for got, want in zip(b["features"], expected["features"], strict=True):
            assert got["shap_value"] == pytest.approx(want["shap_value"], abs=TOL)
            assert got["direction"] == want["direction"]
        assert "not" in b["interpretation"].lower() and "caus" in b["interpretation"].lower()


def test_business_equals_the_phase4_engine(client, direct, frame, customers):
    art, engine = direct["churn"].artifact, direct["engine"]
    seen = set()
    for i in customers:
        r = client.post("/api/v1/business", json=payload_for(frame, i))
        assert r.status_code == 200, r.text
        b = r.json()
        p = float(art.predict_proba(frame.iloc[[i]])[0])
        want = engine.profile(p, frame.iloc[i].to_dict(), None).to_dict()
        for key in ("clv", "value_at_risk", "expected_net_benefit", "expected_benefit", "action_cost",
                    "action_success_rate"):
            assert b[key] == pytest.approx(want[key], abs=TOL), key
        for key in ("intervention_decision", "recommended_action_id", "risk_band", "currency"):
            assert b[key] == want[key], key
        assert len(b["action_evaluations"]) == len(want["action_evaluations"])
        assert b["explanation"]["model_explanation"] and "caus" in b["notice"].lower()
        seen.add(b["intervention_decision"])
    assert seen == {"INTERVENE", "DO_NOT_INTERVENE"}                      # the sample exercises both decisions


def test_segment_equals_the_locked_phase5_assignment(client, direct, frame, customers):
    from ml.segmentation import assign_customers
    seg = direct["seg"]
    names = set()
    for i in customers:
        r = client.post("/api/v1/segment", json=payload_for(frame, i))
        assert r.status_code == 200, r.text
        b, want = r.json(), assign_customers(seg.model, seg.segment_names, frame.iloc[[i]], None)[0]
        assert (b["segment_id"], b["segment_name"]) == (want.segment_id, want.segment_name)
        assert b["distance_to_centroid"] == pytest.approx(want.distance_to_centroid, abs=TOL)
        assert b["segment_count"] == 3 and b["segment_model_version"] == "5.0.0"
        assert "not a probability" in b["note"]
        names.add(b["segment_name"])
    assert len(names) >= 2


def test_customer_intelligence_equals_the_individual_endpoints(client, frame, customers):
    for i in customers[:8]:
        req = payload_for(frame, i)
        combined = client.post("/api/v1/customer-intelligence", json=req)
        assert combined.status_code == 200, combined.text
        b = combined.json()
        for key, url in (("prediction", "predict"), ("segment", "segment")):
            assert b[key] == client.post(f"/api/v1/{url}", json=req).json()
        alone = client.post("/api/v1/business", json=req).json()
        assert b["business"]["churn_probability"] == alone["churn_probability"]
        assert b["business"]["expected_net_benefit"] == alone["expected_net_benefit"]
        assert b["business"]["intervention_decision"] == alone["intervention_decision"]
        assert b["prediction"]["churn_probability"] == b["explanation"]["churn_probability"]


# --------------------------------------------------------------------------------------- hard guarantees
def test_no_kmeans_fit_ever_happens_during_requests(client, frame, customers, monkeypatch):
    from sklearn.cluster import KMeans

    def forbidden(*args, **kwargs):
        raise AssertionError("KMeans was fitted during an API request")

    for name in ("fit", "fit_predict", "fit_transform"):
        monkeypatch.setattr(KMeans, name, forbidden)
    for url in ("segment", "customer-intelligence"):
        for i in customers[:3]:
            assert client.post(f"/api/v1/{url}", json=payload_for(frame, i)).status_code == 200


def test_phase2_pipeline_would_silently_impute_but_the_api_refuses(client, direct, frame):
    """Why the API validates strictly: the Phase 2 pipeline tolerates a missing feature by imputing it."""
    incomplete = frame.iloc[[5]].drop(columns=["tenure"])
    assert 0.0 <= float(direct["churn"].artifact.predict_proba(incomplete)[0]) <= 1.0     # silently "works"
    req = payload_for(frame, 5)
    del req["features"]["tenure"]
    assert_error(client.post("/api/v1/predict", json=req), 422, "INVALID_INPUT")


def test_concurrent_requests_give_identical_results(client, frame, customers):
    reqs = [payload_for(frame, i) for i in customers[:6]]
    serial = [client.post("/api/v1/customer-intelligence", json=r).json() for r in reqs]
    with ThreadPoolExecutor(8) as pool:
        parallel = list(pool.map(lambda r: client.post("/api/v1/customer-intelligence", json=r).json(), reqs * 2))
    assert parallel == serial * 2


# ---------------------------------------------------------------------------------------- fail-closed paths
def _client(**overrides) -> TestClient:
    return TestClient(create_app(settings=Settings(environment="development", **overrides)))


def _assert_no_internals(text: str) -> None:
    for leaked in (str(ROOT), ".joblib", "Traceback", "site-packages"):
        assert leaked not in text, leaked


def test_wrong_pinned_digest_fails_closed(frame):
    c = _client(phase2_expected_sha256="0" * 64)
    r = c.get("/api/v1/readiness")
    assert r.status_code == 503
    assert {x["name"]: x["detail"] for x in r.json()["checks"]}["phase2_model"] == "artifact_sha256_mismatch"
    _assert_no_internals(r.text)
    for url in ("predict", "business", "explain", "customer-intelligence"):
        resp = c.post(f"/api/v1/{url}", json=payload_for(frame, 0))
        assert_error(resp, 503, "CAPABILITY_UNAVAILABLE")
        _assert_no_internals(resp.text)


def test_missing_model_artifact_fails_closed(frame, tmp_path):
    c = _client(project_root=tmp_path)             # an empty project root: nothing to load
    assert c.get("/api/v1/readiness").status_code == 503
    resp = c.post("/api/v1/predict", json=payload_for(frame, 0))
    assert_error(resp, 503, "CAPABILITY_UNAVAILABLE")
    _assert_no_internals(resp.text)
    assert str(tmp_path) not in resp.text


def test_missing_dataset_only_disables_explainability(frame):
    c = _client(dataset_csv_path="ml/data/raw/does_not_exist.csv")
    body = c.get("/api/v1/readiness")
    assert body.status_code == 503
    assert {x["name"]: x["status"] for x in body.json()["checks"]}["explainability"] == "unavailable"
    req = payload_for(frame, 1)
    assert c.post("/api/v1/predict", json=req).status_code == 200
    assert c.post("/api/v1/business", json=req).status_code == 200
    assert c.post("/api/v1/segment", json=req).status_code == 200
    assert_error(c.post("/api/v1/explain", json=req), 503, "CAPABILITY_UNAVAILABLE")
    assert_error(c.post("/api/v1/customer-intelligence", json=req), 503, "CAPABILITY_UNAVAILABLE")


def test_segmentation_that_is_not_the_locked_k3_is_refused(frame):
    c = _client(expected_segmentation_k=4)
    checks = {x["name"]: x["detail"] for x in c.get("/api/v1/readiness").json()["checks"]}
    assert checks["segmentation"] == "segmentation_k_differs_from_locked"
    req = payload_for(frame, 2)
    assert c.post("/api/v1/predict", json=req).status_code == 200
    assert_error(c.post("/api/v1/segment", json=req), 503, "CAPABILITY_UNAVAILABLE")


def test_wrong_phase5_pin_is_refused(frame):
    c = _client(phase5_expected_sha256="1" * 64)
    assert_error(c.post("/api/v1/segment", json=payload_for(frame, 2)), 503, "CAPABILITY_UNAVAILABLE")


def test_tampering_after_start_is_reported_by_readiness(tmp_path, frame):
    """Works on COPIES in a temporary project root; the real artifacts are never touched."""
    models = tmp_path / "models"
    models.mkdir()
    for src in (MODEL, SEGMENTATION):
        for f in src.parent.glob(src.stem + "*"):
            shutil.copy2(f, models / f.name)
    c = _client(project_root=tmp_path, dataset_csv_path=str(CSV), dataset_spec_path=str(SPEC))
    assert c.get("/api/v1/readiness").status_code == 200
    copy = models / MODEL.name
    copy.write_bytes(copy.read_bytes() + b"\x00")                          # modify the copy
    r = c.get("/api/v1/readiness")
    assert r.status_code == 503
    assert {x["name"]: x["detail"] for x in r.json()["checks"]}["phase2_model"] == "artifact_sha256_mismatch"
    assert hashlib.sha256(MODEL.read_bytes()).hexdigest() == LOCKED_PHASE2_SHA256       # the real one is intact


def test_the_real_adapter_is_not_a_test_double():
    from app.services.adapters.phase15_adapter import Phase15Adapter
    assert create_app(settings=SETTINGS).state.services.adapter.__class__ is Phase15Adapter
    assert Path(MODEL).name == "trichurn_churn_model_v2.0.0.joblib"
