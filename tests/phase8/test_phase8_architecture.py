"""Static guarantees for Phase 8: no training, no model replacement, no hidden dependencies, no secrets/paths."""
from __future__ import annotations

import ast
import re
import subprocess
import sys
from pathlib import Path

from tests.phase8.conftest import ROOT

MLOPS = ROOT / "mlops"
FILES = sorted(MLOPS.rglob("*.py")) + [ROOT / "scripts" / "run_phase8_registry.py",
                                       ROOT / "app" / "services" / "model_lifecycle.py",
                                       ROOT / "app" / "api" / "routes" / "model_lifecycle.py",
                                       ROOT / "app" / "schemas" / "model_lifecycle.py"]
ENV_VARS = {"MLFLOW_TRACKING_URI", "MLFLOW_ARTIFACT_LOCATION", "MLFLOW_EXPERIMENT_NAME", "MLFLOW_MODEL_NAME",
            "MLFLOW_MODEL_VERSION", "TRICHURN_MODEL_PATH", "TRICHURN_MODEL_SHA256"}


def _tree(path: Path) -> ast.AST:
    return ast.parse(path.read_text(encoding="utf-8"))


def test_the_package_is_not_named_mlflow_and_does_not_shadow_the_library():
    assert MLOPS.is_dir() and not (ROOT / "mlflow").exists() and not (ROOT / "mlflow.py").exists()


def test_importing_mlops_does_not_import_mlflow_or_the_ml_stack():
    code = ("import sys, mlops; "
            "bad=[m for m in ('mlflow','sklearn','shap','xgboost','ml') if m in sys.modules]; print(bad)")
    out = subprocess.run([sys.executable, "-c", code], cwd=ROOT, capture_output=True, text=True, check=True)
    assert out.stdout.strip() == "[]"


def test_mlflow_is_only_ever_imported_inside_functions():
    for path in MLOPS.rglob("*.py"):
        for node in _tree(path).body:                                  # module level only
            names = [a.name for a in node.names] if isinstance(node, ast.Import) else \
                [node.module or ""] if isinstance(node, ast.ImportFrom) else []
            assert not any(n.split(".")[0] == "mlflow" for n in names), f"{path.name} imports mlflow at module level"


def test_the_application_package_never_imports_mlflow():
    for path in (ROOT / "app").rglob("*.py"):
        for node in ast.walk(_tree(path)):
            names = [a.name for a in node.names] if isinstance(node, ast.Import) else \
                [node.module or ""] if isinstance(node, ast.ImportFrom) else []
            assert not any(n.split(".")[0] == "mlflow" for n in names), path


def test_phase8_never_trains_fits_or_overwrites_models():
    forbidden = {"fit", "fit_transform", "fit_predict", "partial_fit", "dump", "write_bytes", "write_text",
                 "unlink", "rename", "rmtree", "copyfile", "copy2", "move", "remove", "replace"}
    for path in FILES:
        for node in ast.walk(_tree(path)):
            if isinstance(node, ast.Attribute):
                assert node.attr not in forbidden, f"{path.name}:{node.lineno} uses .{node.attr}"
            if isinstance(node, ast.Name):
                assert node.id not in {"KMeans", "LogisticRegression", "XGBClassifier"}, path.name
            if isinstance(node, ast.Call) and isinstance(node.func, ast.Name) and node.func.id == "open":
                mode = ast.unparse(node.args[1]) if len(node.args) > 1 else ""
                assert not re.search(r"[wax+]", mode), f"{path.name}:{node.lineno} opens a file for writing"


def test_no_machine_specific_paths_or_credentials_in_phase8_code():
    paths = re.compile(r"[A-Za-z]:\\\\|[A-Za-z]:\\|/home/|/Users/|/mnt/|AppData")
    secrets = re.compile(r"(password|passwd|secret|api[_-]?key|auth[_-]?token)\s*[:=]\s*[\"'][^\"']+[\"']"
                         r"|AKIA[0-9A-Z]{8,}|BEGIN (RSA|PRIVATE)", re.IGNORECASE)
    for path in FILES:
        for number, line in enumerate(path.read_text(encoding="utf-8").splitlines(), 1):
            assert not paths.search(line), f"{path.name}:{number} machine-specific path"
            assert not secrets.search(line), f"{path.name}:{number} looks like a credential"


def test_env_example_declares_only_the_documented_variables_with_no_credentials():
    text = (ROOT / ".env.example").read_text(encoding="utf-8")
    assigned = {}
    for line in text.splitlines():
        line = line.strip()
        if line and not line.startswith("#"):
            key, _, value = line.partition("=")
            assigned[key.strip()] = value.strip()
    assert set(assigned) <= ENV_VARS
    assert not any("@" in v or "token" in v.lower() for v in assigned.values())       # no user:pass@host, no tokens


def test_requirements_phase8_adds_only_mlflow():
    lines = [ln.strip() for ln in (ROOT / "requirements-phase8.txt").read_text().splitlines()
             if ln.strip() and not ln.strip().startswith("#")]
    assert len(lines) == 1 and lines[0].startswith("mlflow")


def test_local_mlflow_store_is_git_ignored_by_its_own_gitignore():
    ignore = (ROOT / "mlflow_local" / ".gitignore").read_text()
    assert "*" in ignore and "!.gitignore" in ignore
