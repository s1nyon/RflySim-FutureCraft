#!/usr/bin/env python3
"""Require every tracked script to appear in exactly one inventory category."""

from __future__ import annotations

import argparse
import re
import subprocess
import sys
from collections import Counter
from pathlib import Path


CATEGORIES = {
    "Public entry",
    "Protected internal",
    "Focused diagnostic",
    "Hazard-disabled",
    "Historical compatibility",
}
HEADING_RE = re.compile(r"^##\s+(.+?)\s*$")
PATH_RE = re.compile(r"`(scripts/[^`]+)`")


def tracked_scripts(project_root: Path, errors: list[str]) -> set[str]:
    result = subprocess.run(
        ["git", "ls-files", "--", "scripts"],
        cwd=project_root,
        capture_output=True,
        text=True,
        check=False,
    )
    if result.returncode != 0:
        errors.append(f"git ls-files scripts failed: {result.stderr.strip() or result.returncode}")
        return set()
    return {
        line.strip().replace("\\", "/")
        for line in result.stdout.splitlines()
        if line.strip() and line.strip().replace("\\", "/") != "scripts/README.md"
    }


def inventory_entries(inventory: Path, errors: list[str]) -> list[str]:
    try:
        lines = inventory.read_text(encoding="utf-8").splitlines()
    except OSError as exc:
        errors.append(f"cannot read scripts/README.md: {exc}")
        return []

    headings: list[str] = []
    entries: list[str] = []
    current_category: str | None = None
    table_seen: set[str] = set()
    for line in lines:
        heading = HEADING_RE.match(line)
        if heading:
            current_category = heading.group(1)
            headings.append(current_category)
            continue
        if current_category not in CATEGORIES or not line.lstrip().startswith("|"):
            continue
        paths = PATH_RE.findall(line)
        if paths:
            table_seen.add(current_category)
            entries.extend(path.replace("\\", "/") for path in paths)

    heading_counts = Counter(headings)
    missing_headings = sorted(CATEGORIES - set(headings))
    unknown_headings = sorted(set(headings) - CATEGORIES)
    duplicate_headings = sorted(name for name, count in heading_counts.items() if count > 1)
    if missing_headings:
        errors.append(f"missing inventory category headings: {missing_headings}")
    if unknown_headings:
        errors.append(f"unknown inventory category headings: {unknown_headings}")
    if duplicate_headings:
        errors.append(f"duplicate inventory category headings: {duplicate_headings}")
    missing_tables = sorted(CATEGORIES - table_seen)
    if missing_tables:
        errors.append(f"categories without a classification table: {missing_tables}")
    return entries


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--project-root", required=True, type=Path)
    args = parser.parse_args()
    project_root = args.project_root.resolve()
    errors: list[str] = []

    tracked = tracked_scripts(project_root, errors)
    entries = inventory_entries(project_root / "scripts" / "README.md", errors)
    counts = Counter(entries)
    duplicates = sorted(path for path, count in counts.items() if count != 1)
    missing = sorted(tracked - set(entries))
    extra = sorted(set(entries) - tracked)
    if duplicates:
        errors.append(f"scripts classified more than once: {duplicates}")
    if missing:
        errors.append(f"tracked scripts missing from inventory: {missing}")
    if extra:
        errors.append(f"inventory paths are not tracked scripts: {extra}")

    if errors:
        for error in errors:
            print(f"[FAIL] {error}", file=sys.stderr)
        return 1
    print(f"[PASS] {len(tracked)} tracked scripts are classified exactly once")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
