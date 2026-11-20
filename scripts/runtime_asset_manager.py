"""Private runtime-asset retrieval and validation for production startup."""
from __future__ import annotations

import hashlib
import json
import os
import re
import tempfile
from pathlib import Path
from typing import Any
from urllib.error import HTTPError, URLError
from urllib.parse import quote, urlencode
from urllib.request import HTTPRedirectHandler, Request, build_opener

from app.core.config import (
    DEFAULT_DATASET_CSV,
    DEFAULT_DATASET_SPEC,
    DEFAULT_PHASE2_MODEL,
    DEFAULT_PHASE5_MODEL,
    Settings,
)
from app.services.customer_directory import load_customer_records
from ml.config import load_config
from ml.errors import IngestionError, ValidationError
from ml.pipelines.ingestion import DatasetSpec, load_csv
from ml.pipelines.validation import validate_dataset
from mlops.integrity import sha256_file

MAX_ASSET_BYTES = 100 * 1024 * 1024
RUNTIME_ASSETS = (
    "ml/data/raw/telco_churn.csv",
    "models/trichurn_churn_model_v2.0.0.joblib",
    "models/trichurn_churn_model_v2.0.0.metadata.json",
    "models/trichurn_segmentation_v5.0.0.joblib",
    "models/trichurn_segmentation_v5.0.0.metadata.json",
    "data/telco_churn_live.csv",
)
_REPOSITORY = re.compile(r"^[A-Za-z0-9_.-]+/[A-Za-z0-9_.-]+$")


class RuntimeAssetError(RuntimeError):
    """A missing, invalid, or unverifiable production runtime asset."""


class _NoRedirect(HTTPRedirectHandler):
    def redirect_request(self, _req: Request, _fp: Any, _code: int, _msg: str,
                         _headers: Any, _newurl: str) -> None:
        raise URLError("redirects are not permitted for private runtime assets")


def _read_manifest(path: Path) -> dict[str, Any]:
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        raise RuntimeAssetError("The runtime asset integrity manifest is unavailable or invalid.") from None
    if not isinstance(value, dict) or not isinstance(value.get("files"), dict):
        raise RuntimeAssetError("The runtime asset integrity manifest is unavailable or invalid.")
    return value


def _expected_assets(root: Path) -> dict[str, str]:
    integrity_manifest = _read_manifest(root / "configs" / "integrity_manifest.json")
    runtime_manifest = _read_manifest(root / "configs" / "runtime_assets.json")
    result: dict[str, str] = {}
    for relative_path in RUNTIME_ASSETS:
        entries = integrity_manifest["files"] if relative_path != "data/telco_churn_live.csv" \
            else runtime_manifest["files"]
        entry = entries.get(relative_path)
        digest = entry.get("sha256") if isinstance(entry, dict) else None
        if not isinstance(digest, str) or not re.fullmatch(r"[0-9a-f]{64}", digest):
            raise RuntimeAssetError("A required runtime asset has no valid SHA-256 pin.")
        result[relative_path] = digest
    return result


def _github_request(url: str, token: str, *, raw: bool) -> Any:
    headers = {
        "Accept": "application/vnd.github.raw+json" if raw else "application/vnd.github+json",
        "Authorization": f"Bearer {token}",
        "User-Agent": "TriChurn-runtime-assets",
        "X-GitHub-Api-Version": "2022-11-28",
    }
    request = Request(url, headers=headers, method="GET")
    opener = build_opener(_NoRedirect)
    return opener.open(request, timeout=30)


def _verify_private_repository(repository: str, token: str) -> None:
    url = f"https://api.github.com/repos/{repository}"
    try:
        with _github_request(url, token, raw=False) as response:
            metadata = json.loads(response.read(1024 * 1024))
    except (HTTPError, URLError, TimeoutError, OSError, ValueError):
        raise RuntimeAssetError("The private runtime-asset repository could not be verified.") from None
    if not isinstance(metadata, dict) or metadata.get("private") is not True:
        raise RuntimeAssetError("The configured runtime-asset repository must be private.")


def _download_asset(repository: str, ref: str, token: str, relative_path: str, destination: Path,
                    expected_sha256: str) -> None:
    encoded_path = quote(relative_path, safe="/")
    query = urlencode({"ref": ref})
    url = f"https://api.github.com/repos/{repository}/contents/{encoded_path}?{query}"
    destination.parent.mkdir(parents=True, exist_ok=True)
    temporary_path: Path | None = None
    try:
        with _github_request(url, token, raw=True) as response:
            content_length = response.headers.get("Content-Length")
            if content_length is not None and int(content_length) > MAX_ASSET_BYTES:
                raise RuntimeAssetError("A runtime asset exceeds the allowed download size.")
            digest = hashlib.sha256()
            size = 0
            with tempfile.NamedTemporaryFile(dir=destination.parent, prefix=".trichurn-asset-", delete=False) as temp:
                temporary_path = Path(temp.name)
                while True:
                    chunk = response.read(1024 * 1024)
                    if not chunk:
                        break
                    size += len(chunk)
                    if size > MAX_ASSET_BYTES:
                        raise RuntimeAssetError("A runtime asset exceeds the allowed download size.")
                    digest.update(chunk)
                    temp.write(chunk)
        if digest.hexdigest() != expected_sha256:
            raise RuntimeAssetError(f"SHA-256 verification failed for runtime asset {relative_path}.")
        try:
            os.link(temporary_path, destination)
        except FileExistsError:
            if not destination.is_file() or sha256_file(destination) != expected_sha256:
                raise RuntimeAssetError(f"Runtime asset {relative_path} appeared with unexpected bytes.") from None
    except RuntimeAssetError:
        raise
    except (HTTPError, URLError, TimeoutError, OSError, ValueError):
        raise RuntimeAssetError(f"Unable to retrieve runtime asset {relative_path}.") from None
    finally:
        if temporary_path is not None:
            temporary_path.unlink(missing_ok=True)


def _runtime_source(environ: dict[str, str]) -> tuple[str | None, str, str | None]:
    repository = environ.get("TRICHURN_ASSET_REPOSITORY", "").strip()
    token = environ.get("TRICHURN_ASSET_TOKEN", "").strip()
    ref = environ.get("TRICHURN_ASSET_REF", "main").strip()
    if not repository and not token:
        return None, ref, None
    if not _REPOSITORY.fullmatch(repository) or not token or not ref or len(ref) > 255:
        raise RuntimeAssetError("Private runtime-asset settings are incomplete or invalid.")
    return repository, ref, token


def _ensure_assets(settings: Settings, environ: dict[str, str]) -> None:
    root = settings.project_root
    if (
        settings.phase2_model_path != DEFAULT_PHASE2_MODEL
        or settings.phase5_model_path != DEFAULT_PHASE5_MODEL
        or settings.dataset_csv_path != DEFAULT_DATASET_CSV
        or settings.dataset_spec_path != DEFAULT_DATASET_SPEC
    ):
        raise RuntimeAssetError("Production runtime paths must match the locked asset manifest.")

    expected = _expected_assets(root)
    missing: list[str] = []
    for relative_path, digest in expected.items():
        path = root / relative_path
        if not path.is_file():
            missing.append(relative_path)
        elif sha256_file(path) != digest:
            raise RuntimeAssetError(f"SHA-256 verification failed for runtime asset {relative_path}.")

    if missing:
        repository, ref, token = _runtime_source(environ)
        if repository is None or token is None:
            raise RuntimeAssetError(
                "Required runtime assets are missing; configure a private GitHub asset repository and read-only token."
            )
        _verify_private_repository(repository, token)
        for relative_path in missing:
            _download_asset(repository, ref, token, relative_path, root / relative_path, expected[relative_path])


def _validate_demo_dataset(path: Path) -> None:
    try:
        load_customer_records(path)
    except (OSError, ValueError, TypeError):
        raise RuntimeAssetError("The private demo customer dataset failed schema validation.") from None


def _validate_training_dataset(settings: Settings) -> None:
    root = settings.project_root
    try:
        path = settings.resolve(settings.dataset_csv_path)
        frame = load_csv(path)
        spec = DatasetSpec.from_yaml(settings.resolve(settings.dataset_spec_path))
        quality = load_config("quality", config_dir=root / "configs")
        report = validate_dataset(frame, spec, quality)
        report.raise_if_invalid()
    except (OSError, IngestionError, ValidationError, KeyError, TypeError, ValueError):
        raise RuntimeAssetError("The locked model dataset failed startup schema validation.") from None


def prepare_runtime_assets(settings: Settings, environ: dict[str, str] | None = None) -> None:
    """Download only missing pinned files from a verified private repository, then validate both CSV schemas."""
    _ensure_assets(settings, dict(os.environ) if environ is None else environ)
    _validate_training_dataset(settings)
    _validate_demo_dataset(settings.project_root / "data" / "telco_churn_live.csv")
