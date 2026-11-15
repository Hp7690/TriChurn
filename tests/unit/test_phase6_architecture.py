"""Phase 6 architecture guarantees, enforced by static analysis of the ``app`` package.

frontend -> app.api (routes) -> app.services -> app.services.adapters -> ml (Phase 1-5)
"""
from __future__ import annotations

import ast
import re
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]
APP = ROOT / "app"
ADAPTER = APP / "services" / "adapters" / "phase15_adapter.py"
FILES = sorted(APP.rglob("*.py"))


def _tree(path: Path) -> ast.AST:
    return ast.parse(path.read_text(encoding="utf-8"))


def _imports(path: Path) -> list[tuple[str, ast.AST]]:
    out = []
    for node in ast.walk(_tree(path)):
        if isinstance(node, ast.Import):
            out += [(a.name, node) for a in node.names]
        elif isinstance(node, ast.ImportFrom) and node.module and node.level == 0:
            out.append((node.module, node))
    return out


def _rel(path: Path) -> str:
    return path.relative_to(ROOT).as_posix()


def test_overlay_files_are_present():
    assert len(FILES) >= 30 and ADAPTER.is_file()


def test_only_the_real_adapter_imports_ml_and_only_inside_default_bindings():
    for path in FILES:
        tree = _tree(path)                                    # ONE parse, so node identities are comparable
        offenders = [n for n in ast.walk(tree)
                     if (isinstance(n, ast.Import) and any(a.name.split(".")[0] == "ml" for a in n.names))
                     or (isinstance(n, ast.ImportFrom) and n.level == 0 and (n.module or "").split(".")[0] == "ml")]
        if path != ADAPTER:
            assert not offenders, f"{_rel(path)} imports ml"
            continue
        fn = next(n for n in ast.walk(tree) if isinstance(n, ast.FunctionDef) and n.name == "default_bindings")
        inside = {id(n) for n in ast.walk(fn)}
        assert offenders and all(id(n) in inside for n in offenders), "ml imports must live in default_bindings()"


def test_no_ml_framework_or_io_libraries_in_the_api_layer():
    banned = {"sklearn", "shap", "xgboost", "joblib", "scipy", "pickle", "dill"}
    heavy_allowed_in_adapter_only = {"pandas", "numpy"}
    for path in FILES:
        for name, _ in _imports(path):
            root = name.split(".")[0]
            assert root not in banned, f"{_rel(path)} imports {root}"
            if root in heavy_allowed_in_adapter_only:
                assert path == ADAPTER, f"{_rel(path)} imports {root}; only the adapter handles data frames"


def test_routes_only_talk_to_services_and_schemas():
    for path in sorted((APP / "api").rglob("*.py")):
        for name, _ in _imports(path):
            assert not name.startswith(("app.services.adapters", "app.services.artifact_loader")), (
                f"{_rel(path)} must not touch adapters/artifacts directly ({name})")
            assert name.split(".")[0] != "ml"


def test_services_do_not_depend_on_the_http_layer_or_the_real_adapter():
    for path in sorted((APP / "services").rglob("*.py")):
        for name, _ in _imports(path):
            assert not name.startswith("app.api"), f"{_rel(path)} imports the HTTP layer"
    real = "app.services.adapters.phase15_adapter"
    users = [_rel(p) for p in FILES if any(n == real for n, _ in _imports(p))]
    assert users == ["app/services/adapters/factory.py"]          # only the factory may construct the real adapter


def test_core_and_schemas_are_leaf_layers():
    for folder in ("core", "schemas"):
        for path in sorted((APP / folder).rglob("*.py")):
            for name, _ in _imports(path):
                assert not name.startswith(("app.services", "app.api")), f"{_rel(path)} imports {name}"


def test_only_the_composition_root_chooses_the_adapter():
    users = [_rel(p) for p in FILES if any(n.startswith("app.services.adapters.factory") for n, _ in _imports(p))]
    assert users == ["app/main.py"]


def test_the_api_never_fits_retrains_or_writes_artifacts():
    forbidden_attrs = {"fit", "fit_transform", "fit_predict", "partial_fit", "dump", "write_bytes", "write_text",
                       "unlink", "rename", "rmtree", "copyfile", "copy2", "move"}
    for path in FILES:
        for node in ast.walk(_tree(path)):
            if isinstance(node, ast.Attribute):
                assert node.attr not in forbidden_attrs, f"{_rel(path)}:{node.lineno} uses .{node.attr}"
            if isinstance(node, ast.Name):
                assert node.id != "KMeans", f"{_rel(path)}:{node.lineno} references KMeans"
            if isinstance(node, ast.Call) and isinstance(node.func, ast.Name) and node.func.id == "open":
                mode = ast.unparse(node.args[1]) if len(node.args) > 1 else ""
                assert not re.search(r"[wax+]", mode), f"{_rel(path)}:{node.lineno} opens a file for writing"
        # an open() on Path objects: only reading is ever done
        assert ".open(\"w" not in path.read_text() and ".open('w" not in path.read_text()


def test_no_business_or_model_formulas_in_the_api_layer():
    tokens = ("clv", "success_rate", "probability", "cost", "enb", "shap", "churn")
    for path in FILES:
        for node in ast.walk(_tree(path)):
            if isinstance(node, ast.BinOp) and isinstance(node.op, ast.Mult | ast.Sub | ast.Div | ast.Add):
                text = ast.unparse(node).lower()
                if path.name == "errors.py" or path.name == "artifact_loader.py":
                    continue
                assert not any(t in text for t in tokens), f"{_rel(path)}:{node.lineno} computes {text!r}"


def test_no_test_double_or_test_import_in_the_application_package():
    for path in FILES:
        for name, _ in _imports(path):
            assert name.split(".")[0] != "tests", f"{_rel(path)} imports test code"
        for node in ast.walk(_tree(path)):
            if isinstance(node, ast.Assign) and any(isinstance(t, ast.Name) and t.id == "is_test_double"
                                                    for t in node.targets):
                assert ast.unparse(node.value) == "False", f"{_rel(path)} declares a test double"
        assert "class Fake" not in path.read_text() and "class Mock" not in path.read_text()


def test_the_real_adapter_is_not_a_test_double_and_the_fake_lives_in_tests_only():
    from app.services.adapters.phase15_adapter import Phase15Adapter
    from app.services.adapters.unavailable import UnavailableAdapter
    assert Phase15Adapter.is_test_double is False and UnavailableAdapter.is_test_double is False
    assert (ROOT / "tests" / "support" / "fake_adapter.py").is_file()
    assert "TEST-ONLY" in (ROOT / "tests" / "support" / "fake_adapter.py").read_text()


def test_overlay_ships_no_models_datasets_or_environments():
    for folder in ("app", "phase6", "docs"):
        for path in (ROOT / folder).rglob("*") if (ROOT / folder).exists() else []:
            assert path.suffix.lower() not in {".joblib", ".pkl", ".pickle", ".csv", ".parquet", ".h5", ".pt"}, path
    assert not any(part in {".venv", "venv", ".git", ".pytest_cache"} for p in FILES for part in p.parts)


def test_ml_package_does_not_import_the_api_layer():
    ml = ROOT / "ml"
    if not ml.is_dir():
        pytest.skip("ml package not present: standalone overlay run (runs in the merged project)")
    banned = {"app", "fastapi", "starlette", "uvicorn"}
    for path in ml.rglob("*.py"):
        for name, _ in _imports(path):
            assert name.split(".")[0] not in banned, f"{path.relative_to(ROOT)} imports {name}"


def test_no_machine_specific_paths_in_the_application_package():
    pattern = re.compile(r"[A-Za-z]:\\\\|[A-Za-z]:\\|/home/|/Users/|/mnt/|AppData")
    for path in FILES:
        for i, line in enumerate(path.read_text(encoding="utf-8").splitlines(), 1):
            assert not pattern.search(line), f"{_rel(path)}:{i} contains a machine-specific path"
