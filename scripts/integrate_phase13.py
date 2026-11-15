#!/usr/bin/env python3
"""Merge the Phase 13 overlay into an existing TriChurn project WITHOUT overwriting anything.

Default is a DRY RUN: it prints what it would do and changes nothing.

    python scripts/integrate_phase13.py --project-root "C:\\path\\to\\Customer Churn Prediction"          # dry run
    python scripts/integrate_phase13.py --project-root "C:\\path\\to\\Customer Churn Prediction" --apply  # do it

What --apply does
  1. COPY every new Phase 13 file. A file that already exists with different content is a CONFLICT: nothing at all is
     changed and the script exits 1. Identical files are skipped.
  2. PATCH four existing files with the smallest possible additive edits (idempotent; a backup
     ``<file>.phase13.bak`` is written first):
       app/main.py                          import + one register_experience(app, settings) call
       frontend/src/App.tsx                 two imports + two <Route> lines
       frontend/src/components/Sidebar.tsx  one import + ...EXPERIENCE_NAV in the NAV array
       frontend/src/services/api/contract.ts one re-export line
     If an anchor cannot be found (your file differs from the snapshot this was written against) the script does NOT
     guess: it prints the exact manual edit and exits 2. Original line endings (CRLF/LF) are preserved.

It never touches models/, ml/, configs/ (other than the new experience.yaml),
existing tests, requirements.txt or any dependency. It reports the locked Phase 2/5 model hashes before and after.
"""

from __future__ import annotations

import argparse
import ast
import hashlib
import re
import shutil
import sys
from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path

OVERLAY_ROOT = Path(__file__).resolve().parents[1]
SKIP_DIRS = {"__pycache__", "node_modules", ".git", ".venv", "venv", ".pytest_cache", ".ruff_cache", "dist"}
SKIP_SUFFIXES = {".pyc", ".pyo"}
SKIP_NAMES = {"PHASE13_MANIFEST_SHA256.txt"}

LOCKED = {
    "models/trichurn_churn_model_v2.0.0.joblib": "db399a55f650c6681e1caaf52257f909777e2c5fada3af5911370ddf5b8ff1ad",
    "models/trichurn_segmentation_v5.0.0.joblib": "38423c9cf19b05aa35b72acd44ea3a8af4c3775a1e6cf2bb739ee1972dc05927",
}


# ------------------------------------------------------------------------------------------------ helpers
def sha256(path: Path) -> str:
    h = hashlib.sha256()
    with open(path, "rb") as fh:
        for block in iter(lambda: fh.read(1 << 20), b""):
            h.update(block)
    return h.hexdigest()


def overlay_files() -> list[Path]:
    out: list[Path] = []
    for p in sorted(OVERLAY_ROOT.rglob("*")):
        rel = p.relative_to(OVERLAY_ROOT)
        if (
            not p.is_file()
            or any(part in SKIP_DIRS for part in rel.parts)
            or p.suffix in SKIP_SUFFIXES
            or p.name in SKIP_NAMES
        ):
            continue
        out.append(rel)
    return out


def newline_near(lines: list[str], index: int) -> str:
    for i in (index, index - 1, index + 1):
        if 0 <= i < len(lines):
            if lines[i].endswith("\r\n"):
                return "\r\n"
            if lines[i].endswith("\n"):
                return "\n"
    return "\n"


def insert_line(lines: list[str], index: int, text: str) -> None:
    nl = newline_near(lines, index)
    if index > 0 and index == len(lines) and not lines[-1].endswith(("\n", "\r\n")):
        lines[-1] += nl
    lines.insert(index, text + nl)


@dataclass
class PatchResult:
    status: str  # applied | already | manual | conflict
    new_text: str | None
    message: str
    manual: str = ""


# ------------------------------------------------------------------------------------------------ patches
IMPORT_PY = "from app.api.routes.experience import register_experience"
CALL_PY = "register_experience(app, settings)"


def patch_main(text: str) -> PatchResult:
    if "register_experience" in text:
        return PatchResult("already", None, "register_experience is already present.")
    manual = f"Add `{IMPORT_PY}` with the other imports and `{CALL_PY}` just before `return app` in create_app()."
    try:
        tree = ast.parse(text)
        fn = next(n for n in tree.body if isinstance(n, ast.FunctionDef) and n.name == "create_app")
        returns = [
            n for n in fn.body if isinstance(n, ast.Return) and isinstance(n.value, ast.Name) and n.value.id == "app"
        ]
        has_settings = any(a.arg == "settings" for a in fn.args.args) or any(
            isinstance(n, ast.Assign) and any(isinstance(t, ast.Name) and t.id == "settings" for t in n.targets)
            for n in fn.body
        )
        imports = [n for n in tree.body if isinstance(n, (ast.Import, ast.ImportFrom))]
        if not returns or not imports or not has_settings:
            raise StopIteration
    except (StopIteration, SyntaxError):
        return PatchResult("manual", None, "Could not find create_app() with `settings` and `return app`.", manual)
    ret = returns[-1]
    lines = text.splitlines(keepends=True)
    insert_line(lines, ret.lineno - 1, " " * ret.col_offset + CALL_PY)
    routes_import = next((n for n in imports if isinstance(n, ast.ImportFrom) and n.module == "app.api.routes"), None)
    anchor = (routes_import or imports[-1]).end_lineno
    insert_line(lines, anchor, IMPORT_PY)
    return PatchResult("applied", "".join(lines), "Added import and register_experience call.")


PAGE_IMPORTS = {
    "ExperiencePage": "import { ExperiencePage } from './pages/ExperiencePage';",
    "LifecyclePage": "import { LifecyclePage } from './pages/LifecyclePage';",
}
ROUTES = [
    '<Route path="experience" element={<ExperiencePage />} />',
    '<Route path="experience-lifecycle" element={<LifecyclePage />} />',
]


def patch_app(text: str) -> PatchResult:
    if "ExperiencePage" in text and "LifecyclePage" in text:
        return PatchResult("already", None, "Experience routes are already present.")
    manual = (
        "Add imports of ExperiencePage and LifecyclePage from './pages/...' and, before the catch-all route, "
        + " and ".join(ROUTES)
    )
    if re.search(r'path="(experience|experience-lifecycle)"', text):
        return PatchResult(
            "conflict", None, "A route named 'experience' or 'experience-lifecycle' already exists.", manual
        )
    lines = text.splitlines(keepends=True)
    star = next((i for i, row in enumerate(lines) if '<Route path="*"' in row), None)
    page_idx = [i for i, row in enumerate(lines) if re.match(r"import .* from '\./pages/", row)]
    if star is None or not page_idx:
        return PatchResult("manual", None, 'Could not find the catch-all <Route path="*"> or the page imports.', manual)
    indent = re.match(r"\s*", lines[star]).group(0)
    for route in reversed(ROUTES):
        insert_line(lines, star, indent + route)
    for name in ("LifecyclePage", "ExperiencePage"):
        key = re.search(r"\./pages/(\w+)", PAGE_IMPORTS[name]).group(1)
        idxs = [i for i, row in enumerate(lines) if re.match(r"import .* from '\./pages/", row)]
        pos = idxs[-1] + 1
        for i in idxs:
            if re.search(r"\./pages/(\w+)", lines[i]).group(1) > key:
                pos = i
                break
        insert_line(lines, pos, PAGE_IMPORTS[name])
    return PatchResult("applied", "".join(lines), "Added 2 imports and 2 routes.")


def patch_sidebar(text: str) -> PatchResult:
    if "EXPERIENCE_NAV" in text:
        return PatchResult("already", None, "EXPERIENCE_NAV is already used.")
    manual = "Add `import { EXPERIENCE_NAV } from './experienceNav';` and `...EXPERIENCE_NAV,` inside the NAV array."
    lines = text.splitlines(keepends=True)
    start = next((i for i, row in enumerate(lines) if re.match(r"const NAV\b.*=\s*\[\s*$", row)), None)
    if start is None:
        return PatchResult("manual", None, "Could not find `const NAV ... = [`.", manual)
    end = next((i for i in range(start + 1, len(lines)) if re.match(r"^\];?\s*$", lines[i])), None)
    if end is None:
        return PatchResult("manual", None, "Could not find the end of the NAV array.", manual)
    settings_line = next((i for i in range(start + 1, end) if "'/settings'" in lines[i]), end)
    insert_line(lines, settings_line, "  ...EXPERIENCE_NAV,")
    imports = [i for i, row in enumerate(lines[:start]) if row.startswith("import ")]
    if not imports:
        return PatchResult("manual", None, "Could not find the import block.", manual)
    insert_line(lines, imports[-1] + 1, "import { EXPERIENCE_NAV } from './experienceNav';")
    return PatchResult("applied", "".join(lines), "Added EXPERIENCE_NAV import and spread.")


def patch_contract(text: str) -> PatchResult:
    if "EXPERIENCE_ENDPOINTS" in text:
        return PatchResult("already", None, "EXPERIENCE_ENDPOINTS is already exported.")
    nl = "\r\n" if "\r\n" in text else "\n"
    base = text if text.endswith(("\n", "\r\n")) or not text else text + nl
    return PatchResult(
        "applied", base + "export { EXPERIENCE_ENDPOINTS } from './experienceContract';" + nl, "Appended re-export."
    )


PATCHES: list[tuple[str, Callable[[str], PatchResult]]] = [
    ("app/main.py", patch_main),
    ("frontend/src/App.tsx", patch_app),
    ("frontend/src/components/Sidebar.tsx", patch_sidebar),
    ("frontend/src/services/api/contract.ts", patch_contract),
]


# ------------------------------------------------------------------------------------------------ main
def locked_report(root: Path) -> list[str]:
    rows = []
    for rel, expected in LOCKED.items():
        p = root / rel
        state = "MISSING" if not p.is_file() else ("OK" if sha256(p) == expected else "MISMATCH")
        rows.append(f"  {state:9} {rel}")
    return rows


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--project-root", type=Path, required=True, help="Existing TriChurn project folder.")
    ap.add_argument("--apply", action="store_true", help="Make the changes (default is a dry run).")
    args = ap.parse_args(argv)
    root = args.project_root.resolve()
    if not root.is_dir():
        print(f"ERROR: project root not found: {root}")
        return 1
    if root == OVERLAY_ROOT:
        print("ERROR: --project-root must be your project, not the overlay folder.")
        return 1

    mode = "APPLY" if args.apply else "DRY RUN (nothing will be changed)"
    print(f"Phase 13 integration - {mode}\nProject: {root}\n\nLocked artifacts BEFORE:")
    print("\n".join(locked_report(root)))

    # ---- 1. copy plan
    to_copy, identical, conflicts = [], [], []
    for rel in overlay_files():
        src, dst = OVERLAY_ROOT / rel, root / rel
        if not dst.exists():
            to_copy.append(rel)
        elif dst.is_file() and sha256(src) == sha256(dst):
            identical.append(rel)
        else:
            conflicts.append(rel)
    print(f"\nNew files: {len(to_copy)} to copy, {len(identical)} already identical, {len(conflicts)} CONFLICT(S)")
    for rel in conflicts:
        print(f"  CONFLICT (exists with different content, will not overwrite): {rel.as_posix()}")

    # ---- 2. patch plan
    results: list[tuple[str, PatchResult]] = []
    for rel, fn in PATCHES:
        path = root / rel
        if not path.is_file():
            results.append(
                (
                    rel,
                    PatchResult(
                        "manual",
                        None,
                        "File not found.",
                        f"Integrate manually: see PHASE13_INTEGRATION_GUIDE.md ({rel}).",
                    ),
                )
            )
            continue
        results.append((rel, fn(path.read_bytes().decode("utf-8"))))
    print("\nIntegration patches:")
    for rel, res in results:
        label = "WILL-APPLY" if (res.status == "applied" and not args.apply) else res.status.upper()
        print(f"  {label:10} {rel} - {res.message}")
        if res.manual and res.status in ("manual", "conflict"):
            print(f"            MANUAL: {res.manual}")

    if conflicts or any(r.status == "conflict" for _, r in results):
        print("\nSTOPPED: resolve the conflicts above first. Nothing was changed.")
        return 1
    if not args.apply:
        print("\nDry run complete. Re-run with --apply to make these changes.")
        return 0 if all(r.status != "manual" for _, r in results) else 2

    # ---- apply
    for rel in to_copy:
        dst = root / rel
        dst.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(OVERLAY_ROOT / rel, dst)
    for rel, res in results:
        if res.status != "applied" or res.new_text is None:
            continue
        path = root / rel
        n, backup = 0, path.with_name(path.name + ".phase13.bak")
        while backup.exists():
            n += 1
            backup = path.with_name(f"{path.name}.phase13.bak{n}")
        shutil.copy2(path, backup)
        with open(path, "w", encoding="utf-8", newline="") as fh:
            fh.write(res.new_text)
        print(f"  patched {rel} (backup: {backup.name})")
    print(f"\nCopied {len(to_copy)} file(s).\n\nLocked artifacts AFTER:")
    print("\n".join(locked_report(root)))
    manual = [rel for rel, r in results if r.status == "manual"]
    if manual:
        print("\nACTION NEEDED: apply the MANUAL edits above for: " + ", ".join(manual))
        return 2
    print("\nDone. Next: pip install -r requirements-phase13.txt, run the tests, then start the app.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
