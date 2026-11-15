#!/usr/bin/env python3
"""Verify the locked Phase 2 and Phase 5 model hashes. Read-only; exits 1 if any hash differs or a file is missing.

Usage:  python scripts/verify_phase13_locked_artifacts.py [--project-root PATH]
"""

from __future__ import annotations

import argparse
import hashlib
import sys
from pathlib import Path

LOCKED = {
    "Phase 2 churn model": (
        "models/trichurn_churn_model_v2.0.0.joblib",
        "db399a55f650c6681e1caaf52257f909777e2c5fada3af5911370ddf5b8ff1ad",
    ),
    "Phase 5 segmentation model": (
        "models/trichurn_segmentation_v5.0.0.joblib",
        "38423c9cf19b05aa35b72acd44ea3a8af4c3775a1e6cf2bb739ee1972dc05927",
    ),
}


def sha256_of(path: Path) -> str:
    digest = hashlib.sha256()
    with open(path, "rb") as fh:
        for block in iter(lambda: fh.read(1 << 20), b""):
            digest.update(block)
    return digest.hexdigest()


def verify(root: Path) -> list[tuple[str, str, str, str]]:
    """Return (name, status, expected, actual) rows. status is OK, MISMATCH or MISSING."""
    rows = []
    for name, (rel, expected) in LOCKED.items():
        path = root / rel
        if not path.is_file():
            rows.append((name, "MISSING", expected, "-"))
            continue
        actual = sha256_of(path)
        rows.append((name, "OK" if actual == expected else "MISMATCH", expected, actual))
    return rows


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--project-root", type=Path, default=Path(__file__).resolve().parents[1])
    args = ap.parse_args(argv)
    rows = verify(args.project_root)
    for name, status, expected, actual in rows:
        print(f"{status:9} {name}\n          expected {expected}\n          actual   {actual}")
    failed = [r for r in rows if r[1] != "OK"]
    print("RESULT: " + ("all locked artifacts match" if not failed else f"{len(failed)} problem(s) - DO NOT PROCEED"))
    return 1 if failed else 0


if __name__ == "__main__":
    sys.exit(main())
