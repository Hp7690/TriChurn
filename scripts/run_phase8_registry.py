"""Phase 8 CLI: MLflow tracking + Model Registry + integrity for the EXISTING Phase 2 churn model.

    python scripts/run_phase8_registry.py verify                 # integrity only (offline, no MLflow needed)
    python scripts/run_phase8_registry.py register [--force]     # verify -> log run -> register -> alias 'production'
    python scripts/run_phase8_registry.py status                 # integrity + registry state (read-only)
    python scripts/run_phase8_registry.py fetch --dest DIR       # download the 'production' version and verify it

Configuration: MLFLOW_TRACKING_URI, MLFLOW_ARTIFACT_LOCATION, MLFLOW_EXPERIMENT_NAME, MLFLOW_MODEL_NAME,
MLFLOW_MODEL_VERSION, TRICHURN_MODEL_PATH, TRICHURN_MODEL_SHA256 (see mlops/config.py and .env.example).
Nothing is trained or replaced; the model file is only read. Exit codes: 0 ok, 2 integrity failure, 3 MLflow failure,
4 configuration error.
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from mlops import MlopsConfigurationError, MlopsSettings, ModelIntegrityError, RegistryError  # noqa: E402
from mlops.integrity import verify_model_artifact  # noqa: E402


def _print(obj: object) -> None:
    print(json.dumps(obj, indent=2, sort_keys=True, default=str))


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    sub = parser.add_subparsers(dest="command", required=True)
    reg = sub.add_parser("register", help="log a tracking run and register the verified model")
    reg.add_argument("--force", action="store_true", help="log a NEW run even if a verified run already exists")
    sub.add_parser("verify")
    sub.add_parser("status")
    fetch = sub.add_parser("fetch")
    fetch.add_argument("--dest", required=True)
    args = parser.parse_args(argv)
    try:
        settings = MlopsSettings.from_env()
    except MlopsConfigurationError as exc:
        print(f"CONFIGURATION ERROR: {exc}", file=sys.stderr)
        return 4
    try:
        if args.command == "verify":
            report = verify_model_artifact(
                settings.model_file, settings.model_sha256, metadata_path=settings.metadata_file,
                expected_version=settings.model_version)
            _print(report.to_dict())
            return 0 if report.ok else 2
        if args.command == "status":
            from mlops.status import model_status
            result = model_status(settings, check_registry=True)
            _print(result)
            return 0 if result["status"] == "verified" else 2
        if args.command == "register":
            from mlops.registry import register_verified_model
            from mlops.tracking import log_model_run
            tracked = log_model_run(settings, force=args.force)
            registered = register_verified_model(settings, tracked.run_id)
            _print({"experiment": tracked.experiment_name, "run_id": tracked.run_id, "run_reused": tracked.reused,
                    "metrics": tracked.metrics, "registered_model": registered.model_name,
                    "registry_version": registered.registry_version, "semantic_version": registered.semantic_version,
                    "version_reused": registered.reused, "alias": registered.alias,
                    "artifact_sha256": registered.artifact_sha256})
            return 0
        from mlops.registry import fetch_verified_model
        path = fetch_verified_model(settings, Path(args.dest))
        _print({"fetched_and_verified": True, "file": path.name, "sha256_pinned": settings.model_sha256})
        return 0
    except ModelIntegrityError as exc:
        print(f"INTEGRITY FAILURE: {exc}", file=sys.stderr)
        return 2
    except RegistryError as exc:
        print(f"MLFLOW ERROR: {exc}", file=sys.stderr)
        return 3


if __name__ == "__main__":
    raise SystemExit(main())
