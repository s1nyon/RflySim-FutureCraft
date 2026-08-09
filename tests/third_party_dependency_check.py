#!/usr/bin/env python3
"""Validate the reproducible EGO-Swarm third-party dependency contract."""

from __future__ import annotations

import argparse
import configparser
import subprocess
import sys
from pathlib import Path


EXPECTED_PATH = "third_party/ego-planner-swarm"
EXPECTED_URL = "https://github.com/s1nyon/ego-planner-swarm.git"
EXPECTED_ENV_FRAGMENT = "/future_aircraft_sim/third_party/ego-planner-swarm"
FORMER_PATHS = (
    b"external" + b"/ego-planner-swarm",
    b"external" + b"\\ego-planner-swarm",
)
ACTIVE_ROOTS = ("config", "scripts", ".agents")
ACTIVE_FILES = ("README.md", "AGENTS.md")


def check_gitmodules(project_root: Path, errors: list[str]) -> None:
    gitmodules = project_root / ".gitmodules"
    if not gitmodules.is_file():
        errors.append(".gitmodules is missing")
        return

    parser = configparser.ConfigParser()
    try:
        parser.read(gitmodules, encoding="utf-8")
    except configparser.Error as exc:
        errors.append(f".gitmodules is invalid: {exc}")
        return

    matches = [
        section
        for section in parser.sections()
        if parser.get(section, "path", fallback="") == EXPECTED_PATH
        and parser.get(section, "url", fallback="") == EXPECTED_URL
    ]
    if not matches:
        errors.append(
            f".gitmodules must declare path {EXPECTED_PATH!r} with URL {EXPECTED_URL!r}"
        )


def check_environment(project_root: Path, errors: list[str]) -> None:
    env_template = project_root / "config" / "env_template.bat"
    try:
        text = env_template.read_text(encoding="utf-8")
    except OSError as exc:
        errors.append(f"cannot read {env_template.relative_to(project_root)}: {exc}")
        return
    if EXPECTED_ENV_FRAGMENT not in text:
        errors.append(
            f"config/env_template.bat must reference {EXPECTED_ENV_FRAGMENT}"
        )


def active_files(project_root: Path) -> list[Path]:
    files = [project_root / relative for relative in ACTIVE_FILES]
    for relative in ACTIVE_ROOTS:
        root = project_root / relative
        if root.is_dir():
            files.extend(path for path in root.rglob("*") if path.is_file())
    return files


def check_former_paths(project_root: Path, errors: list[str]) -> None:
    for path in active_files(project_root):
        try:
            data = path.read_bytes()
        except OSError as exc:
            errors.append(f"cannot read {path.relative_to(project_root)}: {exc}")
            continue
        if any(former_path in data for former_path in FORMER_PATHS):
            errors.append(
                f"active file still references the former EGO path: {path.relative_to(project_root)}"
            )


def check_submodule(project_root: Path, errors: list[str]) -> None:
    result = subprocess.run(
        ["git", "submodule", "status", "--", EXPECTED_PATH],
        cwd=project_root,
        capture_output=True,
        text=True,
        check=False,
    )
    status = result.stdout.rstrip("\r\n")
    if result.returncode != 0:
        detail = result.stderr.strip() or f"exit {result.returncode}"
        errors.append(f"git submodule status failed: {detail}")
        return
    if not status:
        errors.append(f"git submodule status returned no entry for {EXPECTED_PATH}")
        return
    if status[0] != " ":
        states = {
            "-": "uninitialized",
            "+": "not pinned to the recorded gitlink",
            "U": "in a merge-conflict state",
        }
        state = states.get(status[0], f"in an unknown state ({status[0]!r})")
        errors.append(f"submodule {EXPECTED_PATH} is {state}: {status}")
        return

    dirty_result = subprocess.run(
        ["git", "-C", str(project_root / EXPECTED_PATH), "status", "--porcelain"],
        cwd=project_root,
        capture_output=True,
        text=True,
        check=False,
    )
    if dirty_result.returncode != 0:
        detail = dirty_result.stderr.strip() or f"exit {dirty_result.returncode}"
        errors.append(f"cannot inspect submodule cleanliness: {detail}")
        return
    dirty = dirty_result.stdout.strip()
    if dirty:
        errors.append(f"submodule {EXPECTED_PATH} is dirty: {dirty}")


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--project-root", required=True, type=Path)
    args = parser.parse_args()
    project_root = args.project_root.resolve()

    errors: list[str] = []
    check_gitmodules(project_root, errors)
    check_environment(project_root, errors)
    check_former_paths(project_root, errors)
    check_submodule(project_root, errors)

    if errors:
        for error in errors:
            print(f"[FAIL] {error}", file=sys.stderr)
        return 1
    print("[PASS] EGO-Swarm team-fork submodule is configured, initialized, and path-clean")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
