#!/usr/bin/env python3
"""Scan core/, run.py, and config/ for pack facts (AGENTS.md rule 1).

Fails if:
  1. Any production file imports from tests/.
  2. Any production file contains multi-word strings copied verbatim from tests/fixtures/*.txt.
  3. Any production file contains unexpected numeric literals outside structural/config allowlist.
"""

from __future__ import annotations

import ast
import pathlib
import re
import sys


ROOT = pathlib.Path(__file__).resolve().parent.parent
SCAN_PY_DIRS = [ROOT / "core"]
SCAN_PY_FILES = [ROOT / "run.py"]
FIXTURES_DIR = ROOT / "tests" / "fixtures"

# Structural constants permitted in Python code (loop indices, time/currency base units, HTTP timeout, font weights)
ALLOWED_NUMBERS = {
    -1, 0, 1, 2, 3, 4, 5, 6, 7, 8, 9, 10, 11, 12, 13, 14, 15, 16, 17, 18, 19, 20,
    23, 24, 25, 30, 40, 50, 59, 60, 70, 80, 90, 100, 120, 400, 500, 700, 800,
    1_000, 100_000, 10_000_000,
    0.0, 0.5, 0.6, 1.5, 2.5, 120.0,
}

# Files whose dicts hold natural-language number-word mappings (not event facts)
WORD_MAP_FILES = {"ground.py"}


def _collect_fixture_phrases() -> list[tuple[str, str]]:
    """Extract distinctive 5+ word phrases from tests/fixtures/*.txt."""
    phrases: list[tuple[str, str]] = []
    if not FIXTURES_DIR.exists():
        return phrases
    for fpath in sorted(FIXTURES_DIR.glob("*.txt")):
        text = fpath.read_text(encoding="utf-8")
        for line in text.splitlines():
            clean = line.strip()
            if len(clean) >= 25 and not re.match(r"^\d+\.\s", clean):
                # Take first 40 chars of substantive fixture lines
                snippet = clean[:40].lower()
                phrases.append((fpath.name, snippet))
    return phrases


def _scan_python_file(path: pathlib.Path, fixture_phrases: list[tuple[str, str]]) -> list[str]:
    errors: list[str] = []
    text = path.read_text(encoding="utf-8")
    lower = text.lower()
    rel = path.relative_to(ROOT)

    # 1. No imports from tests/
    tree = ast.parse(text, filename=str(path))
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            for alias in node.names:
                if alias.name == "tests" or alias.name.startswith("tests."):
                    errors.append(f"{rel}:{node.lineno}: forbidden import from tests ({alias.name})")
        elif isinstance(node, ast.ImportFrom):
            mod = node.module or ""
            if mod == "tests" or mod.startswith("tests."):
                errors.append(f"{rel}:{node.lineno}: forbidden import from tests ({mod})")

    # 2. No strings copied from fixtures
    for fname, snippet in fixture_phrases:
        if snippet in lower:
            errors.append(f"{rel}: contains text copied from fixture '{fname}': {snippet!r}")

    # 3. No unexpected numeric literals outside structural allowlist
    if path.name not in WORD_MAP_FILES:
        for node in ast.walk(tree):
            if isinstance(node, ast.Constant) and isinstance(node.value, (int, float)) and not isinstance(node.value, bool):
                if node.value not in ALLOWED_NUMBERS:
                    errors.append(f"{rel}:{node.lineno}: unexpected numeric literal {node.value!r} (move design params to config/defaults.toml)")

    return errors


def main() -> int:
    fixture_phrases = _collect_fixture_phrases()
    errors: list[str] = []

    py_files: list[pathlib.Path] = []
    for d in SCAN_PY_DIRS:
        if d.exists():
            py_files.extend(sorted(d.rglob("*.py")))
    for f in SCAN_PY_FILES:
        if f.exists():
            py_files.append(f)

    for pyf in py_files:
        errors.extend(_scan_python_file(pyf, fixture_phrases))

    if errors:
        print("lint_no_facts: FAIL")
        for err in errors:
            print(f"  - {err}")
        return 1

    print(f"lint_no_facts: PASS ({len(py_files)} files scanned, 0 violations)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
