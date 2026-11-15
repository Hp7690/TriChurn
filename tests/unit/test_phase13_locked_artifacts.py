"""Phase 13 must not alter the locked Phase 2 / Phase 5 artifacts. Skipped only when the binaries are absent
(the Phase 13 overlay itself deliberately does not ship them)."""

from __future__ import annotations

import importlib.util
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]
SCRIPT = ROOT / "scripts" / "verify_phase13_locked_artifacts.py"


def _load():
    spec = importlib.util.spec_from_file_location("verify_phase13_locked_artifacts", SCRIPT)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_recorded_hashes_are_the_locked_baseline():
    m = _load()
    assert m.LOCKED["Phase 2 churn model"][1] == "db399a55f650c6681e1caaf52257f909777e2c5fada3af5911370ddf5b8ff1ad"
    assert (
        m.LOCKED["Phase 5 segmentation model"][1] == "38423c9cf19b05aa35b72acd44ea3a8af4c3775a1e6cf2bb739ee1972dc05927"
    )


def test_script_fails_on_mismatch_and_missing(tmp_path):
    m = _load()
    (tmp_path / "models").mkdir()
    (tmp_path / "models" / "trichurn_churn_model_v2.0.0.joblib").write_bytes(b"tampered")
    statuses = {r[0]: r[1] for r in m.verify(tmp_path)}
    assert statuses == {"Phase 2 churn model": "MISMATCH", "Phase 5 segmentation model": "MISSING"}
    assert m.main(["--project-root", str(tmp_path)]) == 1


@pytest.mark.skipif(
    not all(
        (ROOT / rel).is_file()
        for rel in ("models/trichurn_churn_model_v2.0.0.joblib", "models/trichurn_segmentation_v5.0.0.joblib")
    ),
    reason="locked model binaries are not in this checkout",
)
def test_real_locked_artifacts_match():
    m = _load()
    assert [r[1] for r in m.verify(ROOT)] == ["OK", "OK"]
    assert m.main(["--project-root", str(ROOT)]) == 0
