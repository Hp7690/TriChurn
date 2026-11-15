"""Phase 9 guarantees, enforced statically. Complements tests/unit/test_phase6_architecture.py."""
from __future__ import annotations

import ast
import hashlib
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
PKG = ROOT / "retention"
FILES = sorted(PKG.rglob("*.py"))
FORBIDDEN_ATTRS = {"fit", "fit_transform", "partial_fit", "dump", "write_bytes", "write_text", "unlink", "rmtree"}


def _imports(path: Path) -> list[str]:
    out = []
    for node in ast.walk(ast.parse(path.read_text(encoding="utf-8"))):
        if isinstance(node, ast.Import):
            out += [a.name for a in node.names]
        elif isinstance(node, ast.ImportFrom) and node.module and node.level == 0:
            out.append(node.module)
    return out


def test_the_package_exists():
    assert len(FILES) >= 10


def test_retention_never_imports_the_api_layer_or_fastapi():
    for path in FILES:
        for name in _imports(path):
            assert name.split(".")[0] not in {"app", "fastapi", "starlette", "pydantic"}, f"{path.name} imports {name}"


def test_no_mlflow_or_phase8_dependencies():
    banned = {"mlflow", "dvc", "airflow", "wandb"}
    for path in [*FILES, *(ROOT / "app").rglob("*.py")]:
        for name in _imports(path):
            assert name.split(".")[0] not in banned, f"{path.name} imports {name}"


def test_nothing_refits_dumps_or_deletes_files():
    for path in FILES:
        for node in ast.walk(ast.parse(path.read_text(encoding="utf-8"))):
            if isinstance(node, ast.Attribute):
                assert node.attr not in FORBIDDEN_ATTRS, f"{path.name}:{node.lineno} uses .{node.attr}"
            if isinstance(node, ast.Name):
                assert node.id not in {"KMeans", "XGBClassifier", "LogisticRegression"}, f"{path.name} refs {node.id}"


def test_ml_is_imported_only_inside_functions_of_the_scoring_module():
    for path in FILES:
        tree = ast.parse(path.read_text(encoding="utf-8"))
        top_level = [n for n in tree.body if isinstance(n, ast.Import | ast.ImportFrom)]
        for node in top_level:
            module = node.module if isinstance(node, ast.ImportFrom) else node.names[0].name
            assert (module or "").split(".")[0] != "ml", f"{path.name} imports ml at module level"


def test_no_uplift_model_or_fabricated_data_is_present():
    banned = ("causalml", "econml", "sklift", "uplift_model", "faker", "random.", "np.random", "numpy.random")
    for path in FILES:
        text = path.read_text(encoding="utf-8")
        for token in banned:
            assert token not in text, f"{path.name} contains {token!r}"


def test_the_source_tree_ships_no_database_or_seed_data():
    for folder in ("retention", "configs", "tests", "app"):
        for pattern in ("*.sqlite3", "*.sqlite", "*.db"):
            assert not list((ROOT / folder).rglob(pattern)), f"{folder} contains a database file"


def test_locked_model_artifacts_keep_their_hashes():
    pins = {"models/trichurn_churn_model_v2.0.0.joblib":
            "db399a55f650c6681e1caaf52257f909777e2c5fada3af5911370ddf5b8ff1ad",
            "models/trichurn_segmentation_v5.0.0.joblib":
            "38423c9cf19b05aa35b72acd44ea3a8af4c3775a1e6cf2bb739ee1972dc05927"}
    for rel, digest in pins.items():
        path = ROOT / rel
        if path.is_file():
            assert hashlib.sha256(path.read_bytes()).hexdigest() == digest
