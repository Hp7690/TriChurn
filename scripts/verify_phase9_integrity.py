"""Phase 9 integrity check (read-only).

Verifies, against the handoff baseline manifest, that:
  * both locked model artifacts still have their exact SHA-256 hashes,
  * every baseline file is unchanged EXCEPT the small allow-list of wiring files Phase 9 had to touch,
  * no Phase 8 / MLflow files or dependencies appeared,
  * no campaign database or seed data ships in the source tree.

Usage:  python scripts/verify_phase9_integrity.py [--baseline HANDOFF_SHA256.txt] [--root .]
Exit code 0 = OK, 1 = a check failed.
"""
from __future__ import annotations

import argparse
import hashlib
import re
import sys
from pathlib import Path

LOCKED = {
    "models/trichurn_churn_model_v2.0.0.joblib": "db399a55f650c6681e1caaf52257f909777e2c5fada3af5911370ddf5b8ff1ad",
    "models/trichurn_segmentation_v5.0.0.joblib": "38423c9cf19b05aa35b72acd44ea3a8af4c3775a1e6cf2bb739ee1972dc05927",
}
# Existing files that Phase 9 modifies (additive wiring only). Anything else that differs is a failure.
ALLOWED_MODIFIED = {
    "app/main.py",
    "frontend/src/App.tsx",
    "frontend/src/main.tsx",
    "frontend/src/components/Sidebar.tsx",
}
BANNED_PATHS = ("mlflow", "mlruns", ".dvc", "airflow")


def sha256(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as fh:
        for chunk in iter(lambda: fh.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


def read_manifest(path: Path) -> dict[str, str]:
    out: dict[str, str] = {}
    for line in path.read_text(encoding="utf-8", errors="replace").splitlines():
        m = re.match(r"^([0-9A-Fa-f]{64})\s+\*?(.+)$", line.strip())
        if m:
            out[m.group(2).replace("\\", "/")] = m.group(1).lower()
    return out


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--root", default=".")
    ap.add_argument("--baseline", default="HANDOFF_SHA256.txt")
    args = ap.parse_args()
    root = Path(args.root).resolve()
    failures: list[str] = []

    for rel, digest in LOCKED.items():
        p = root / rel
        if not p.is_file():
            failures.append(f"MISSING locked artifact: {rel}")
        elif sha256(p) != digest:
            failures.append(f"CHANGED locked artifact: {rel}")
        else:
            print(f"OK   locked artifact {rel} {digest[:16]}...")

    baseline_path = Path(args.baseline)
    if not baseline_path.is_absolute():
        baseline_path = root / baseline_path
    if baseline_path.is_file():
        baseline = read_manifest(baseline_path)
        changed, missing = [], []
        for rel, digest in baseline.items():
            p = root / rel
            if not p.is_file():
                missing.append(rel)
            elif sha256(p) != digest:
                changed.append(rel)
        unexpected = [c for c in changed if c not in ALLOWED_MODIFIED]
        print(f"baseline files: {len(baseline)}; changed: {len(changed)}; missing: {len(missing)}")
        for rel in sorted(changed):
            print(f"{'ALLOWED' if rel in ALLOWED_MODIFIED else 'UNEXPECTED'} modified: {rel}")
        failures += [f"UNEXPECTED modification of baseline file: {c}" for c in unexpected]
        failures += [f"MISSING baseline file: {m}" for m in missing]
    else:
        failures.append(f"baseline manifest not found: {baseline_path}")

    for p in root.rglob("*"):
        rel = p.relative_to(root).as_posix()
        if any(part in BANNED_PATHS for part in rel.split("/")) and "node_modules" not in rel:
            failures.append(f"Phase 8-style artifact present: {rel}")
        if p.suffix in (".sqlite3", ".sqlite", ".db") and "node_modules" not in rel and not rel.startswith("data/"):
            failures.append(f"database file in source tree: {rel}")

    for line in failures:
        print("FAIL", line)
    print("RESULT:", "OK" if not failures else f"{len(failures)} failure(s)")
    return 1 if failures else 0


if __name__ == "__main__":
    sys.exit(main())
