#!/usr/bin/env python3
"""Exercise bounded log cleanup against disposable project roots."""

from __future__ import annotations

import argparse
import json
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path
from typing import Callable


POWERSHELL = "powershell.exe"


def run_process(arguments: list[str], cwd: Path) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        arguments,
        cwd=cwd,
        text=True,
        capture_output=True,
        timeout=30,
        check=False,
    )


def run_cleanup(script: Path, root: Path, execute: bool = False) -> subprocess.CompletedProcess[str]:
    arguments = [
        POWERSHELL,
        "-NoProfile",
        "-ExecutionPolicy",
        "Bypass",
        "-File",
        str(script),
        "-ProjectRoot",
        str(root),
    ]
    if execute:
        arguments.append("-Execute")
    return run_process(arguments, root)


def quote_ps(value: Path) -> str:
    return str(value).replace("'", "''")


def write_manifest(root: Path, stack_id: str, payload: object) -> Path:
    manifest = root / "logs" / "live_stack" / stack_id / "stack_manifest.json"
    manifest.parent.mkdir(parents=True, exist_ok=True)
    if isinstance(payload, str):
        content = payload
    else:
        content = json.dumps(payload)
    manifest.write_text(content, encoding="utf-8")
    return manifest


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--project-root", required=True, type=Path)
    args = parser.parse_args()
    project_root = args.project_root.resolve()
    script = project_root / "scripts" / "maintenance" / "clean_logs.ps1"
    module = project_root / "scripts" / "sim_cli.psm1"
    failures: list[str] = []

    def check(name: str, function: Callable[[], None]) -> None:
        try:
            function()
        except (AssertionError, OSError, subprocess.TimeoutExpired) as exc:
            failures.append(f"{name}: {exc}")

    def check_dry_run_preserves_files() -> None:
        with tempfile.TemporaryDirectory(prefix="log-cleanup-dry-run-") as directory:
            root = Path(directory)
            artifact = root / "logs" / "run-a" / "trace.log"
            artifact.parent.mkdir(parents=True)
            artifact.write_text("evidence", encoding="utf-8")
            result = run_cleanup(script, root)
            combined = result.stdout + result.stderr
            assert result.returncode == 0, combined
            assert artifact.is_file(), "DryRun removed a log artifact"
            assert "[DRY-RUN] remove" in combined, combined
            assert str(artifact.parent).lower() in combined.lower(), combined

    def check_active_manifest_blocks_all_deletion() -> None:
        with tempfile.TemporaryDirectory(prefix="log-cleanup-active-") as directory:
            root = Path(directory)
            ordinary = root / "logs" / "00-ordinary.log"
            ordinary.parent.mkdir(parents=True)
            ordinary.write_text("keep", encoding="utf-8")
            active = write_manifest(
                root,
                "stack-active",
                {"schema_version": 2, "stack_id": "stack-active", "stop": {"clean": False}},
            )
            result = run_cleanup(script, root, execute=True)
            combined = result.stdout + result.stderr
            assert result.returncode == 2, combined
            assert ordinary.is_file(), "cleanup partially deleted before detecting an active stack"
            assert active.is_file(), "cleanup deleted the active stack manifest"

    def check_malformed_manifest_blocks_all_deletion() -> None:
        with tempfile.TemporaryDirectory(prefix="log-cleanup-malformed-") as directory:
            root = Path(directory)
            ordinary = root / "logs" / "00-ordinary.log"
            ordinary.parent.mkdir(parents=True)
            ordinary.write_text("keep", encoding="utf-8")
            malformed = write_manifest(root, "stack-malformed", "{not-json")
            result = run_cleanup(script, root, execute=True)
            combined = result.stdout + result.stderr
            assert result.returncode == 2, combined
            assert ordinary.is_file(), "cleanup partially deleted before detecting a malformed manifest"
            assert malformed.is_file(), "cleanup deleted the malformed stack manifest"

    def check_missing_manifest_blocks_all_deletion() -> None:
        with tempfile.TemporaryDirectory(prefix="log-cleanup-missing-manifest-") as directory:
            root = Path(directory)
            ordinary = root / "logs" / "00-ordinary.log"
            ordinary.parent.mkdir(parents=True)
            ordinary.write_text("keep", encoding="utf-8")
            incomplete = root / "logs" / "live_stack" / "stack-incomplete"
            incomplete.mkdir(parents=True)
            result = run_cleanup(script, root, execute=True)
            combined = result.stdout + result.stderr
            assert result.returncode == 2, combined
            assert ordinary.is_file(), "cleanup partially deleted before detecting a missing manifest"
            assert incomplete.is_dir(), "cleanup deleted an incomplete stack directory"

    def check_nonfile_manifest_blocks_all_deletion() -> None:
        with tempfile.TemporaryDirectory(prefix="log-cleanup-nonfile-manifest-") as directory:
            root = Path(directory)
            ordinary = root / "logs" / "00-ordinary.log"
            ordinary.parent.mkdir(parents=True)
            ordinary.write_text("keep", encoding="utf-8")
            nonfile = root / "logs" / "live_stack" / "stack-nonfile" / "stack_manifest.json"
            nonfile.mkdir(parents=True)
            result = run_cleanup(script, root, execute=True)
            combined = result.stdout + result.stderr
            assert result.returncode == 2, combined
            assert ordinary.is_file(), "cleanup partially deleted before detecting a non-file manifest"
            assert nonfile.is_dir(), "cleanup deleted the non-file manifest path"

    def check_execute_removes_only_log_children() -> None:
        with tempfile.TemporaryDirectory(prefix="log-cleanup-execute-") as directory:
            root = Path(directory)
            artifact = root / "logs" / "run-a" / "trace.log"
            artifact.parent.mkdir(parents=True)
            artifact.write_text("remove", encoding="utf-8")
            write_manifest(
                root,
                "stack-clean",
                {"schema_version": 2, "stack_id": "stack-clean", "stop": {"clean": True}},
            )
            outside = root / "preserve.txt"
            outside.write_text("keep", encoding="utf-8")
            result = run_cleanup(script, root, execute=True)
            combined = result.stdout + result.stderr
            assert result.returncode == 0, combined
            assert (root / "logs").is_dir(), "cleanup removed the logs directory itself"
            assert not any((root / "logs").iterdir()), "cleanup left children under logs"
            assert outside.read_text(encoding="utf-8") == "keep", "cleanup touched an out-of-root file"

    def check_reparse_escape_blocks_all_deletion() -> None:
        with tempfile.TemporaryDirectory(prefix="log-cleanup-reparse-") as directory:
            root = Path(directory)
            logs = root / "logs"
            logs.mkdir()
            ordinary = logs / "00-ordinary.log"
            ordinary.write_text("keep", encoding="utf-8")
            target = root / "outside"
            target.mkdir()
            outside = target / "protected.txt"
            outside.write_text("keep", encoding="utf-8")
            link = logs / "zz-escape"
            create = run_process(
                [
                    POWERSHELL,
                    "-NoProfile",
                    "-Command",
                    (
                        f"New-Item -ItemType Junction -Path '{quote_ps(link)}' "
                        f"-Target '{quote_ps(target)}' -ErrorAction Stop | Out-Null"
                    ),
                ],
                root,
            )
            assert create.returncode == 0, create.stderr or create.stdout
            result = run_cleanup(script, root, execute=True)
            combined = result.stdout + result.stderr
            assert result.returncode == 2, combined
            assert ordinary.is_file(), "cleanup partially deleted before detecting a reparse escape"
            assert link.exists(), "cleanup removed the escaping reparse point"
            assert outside.read_text(encoding="utf-8") == "keep", "cleanup followed the reparse escape"

    def check_reparse_log_root_is_rejected() -> None:
        with tempfile.TemporaryDirectory(prefix="log-cleanup-root-reparse-") as directory:
            fixture = Path(directory)
            root = fixture / "project"
            root.mkdir()
            target = fixture / "outside"
            target.mkdir()
            protected = target / "protected.txt"
            protected.write_text("keep", encoding="utf-8")
            link = root / "logs"
            create = run_process(
                [
                    POWERSHELL,
                    "-NoProfile",
                    "-Command",
                    (
                        f"New-Item -ItemType Junction -Path '{quote_ps(link)}' "
                        f"-Target '{quote_ps(target)}' -ErrorAction Stop | Out-Null"
                    ),
                ],
                root,
            )
            assert create.returncode == 0, create.stderr or create.stdout
            result = run_cleanup(script, root, execute=True)
            combined = result.stdout + result.stderr
            assert result.returncode == 2, combined
            assert link.exists(), "cleanup removed the redirected logs root"
            assert protected.read_text(encoding="utf-8") == "keep", "cleanup followed the redirected logs root"

    def check_missing_logs_is_success() -> None:
        with tempfile.TemporaryDirectory(prefix="log-cleanup-missing-") as directory:
            root = Path(directory)
            result = run_cleanup(script, root, execute=True)
            assert result.returncode == 0, result.stdout + result.stderr
            assert root.is_dir(), "cleanup changed a project root without logs"

    def check_empty_logs_execute_is_idempotent() -> None:
        with tempfile.TemporaryDirectory(prefix="log-cleanup-empty-") as directory:
            root = Path(directory)
            logs = root / "logs"
            logs.mkdir()
            first = run_cleanup(script, root, execute=True)
            assert first.returncode == 0, first.stdout + first.stderr
            assert logs.is_dir() and not any(logs.iterdir()), "first cleanup changed the empty logs root"
            second = run_cleanup(script, root, execute=True)
            assert second.returncode == 0, second.stdout + second.stderr
            assert logs.is_dir() and not any(logs.iterdir()), "repeated cleanup was not idempotent"

    def check_module_delegates_to_maintenance_script() -> None:
        with tempfile.TemporaryDirectory(prefix="log-cleanup-module-") as directory:
            root = Path(directory)
            fixture_script = root / "scripts" / "maintenance" / "clean_logs.ps1"
            fixture_script.parent.mkdir(parents=True)
            shutil.copy2(script, fixture_script)
            artifact = root / "logs" / "run-a" / "trace.log"
            artifact.parent.mkdir(parents=True)
            artifact.write_text("keep", encoding="utf-8")
            command = (
                f"Import-Module -Force '{quote_ps(module)}'; "
                f"exit (Invoke-SimLogCleanup -ProjectRoot '{quote_ps(root)}' -Execute:$false)"
            )
            result = run_process([POWERSHELL, "-NoProfile", "-Command", command], root)
            combined = result.stdout + result.stderr
            assert result.returncode == 0, combined
            assert "[DRY-RUN] remove" in combined, combined
            assert artifact.is_file(), "module delegation changed DryRun semantics"

        with tempfile.TemporaryDirectory(prefix="log-cleanup-module-execute-") as directory:
            root = Path(directory)
            fixture_script = root / "scripts" / "maintenance" / "clean_logs.ps1"
            fixture_script.parent.mkdir(parents=True)
            shutil.copy2(script, fixture_script)
            artifact = root / "logs" / "run-a" / "trace.log"
            artifact.parent.mkdir(parents=True)
            artifact.write_text("remove", encoding="utf-8")
            command = (
                f"Import-Module -Force '{quote_ps(module)}'; "
                f"exit (Invoke-SimLogCleanup -ProjectRoot '{quote_ps(root)}' -Execute:$true)"
            )
            result = run_process([POWERSHELL, "-NoProfile", "-Command", command], root)
            combined = result.stdout + result.stderr
            assert result.returncode == 0, combined
            assert (root / "logs").is_dir(), "module Execute removed the logs root"
            assert not any((root / "logs").iterdir()), "module did not forward Execute"

    check("DryRun preserves files", check_dry_run_preserves_files)
    check("active manifest fails before deletion", check_active_manifest_blocks_all_deletion)
    check("malformed manifest fails before deletion", check_malformed_manifest_blocks_all_deletion)
    check("missing manifest fails before deletion", check_missing_manifest_blocks_all_deletion)
    check("non-file manifest fails before deletion", check_nonfile_manifest_blocks_all_deletion)
    check("Execute removes only log children", check_execute_removes_only_log_children)
    check("reparse escape fails before deletion", check_reparse_escape_blocks_all_deletion)
    check("redirected logs root is rejected", check_reparse_log_root_is_rejected)
    check("missing logs succeeds", check_missing_logs_is_success)
    check("empty logs Execute is idempotent", check_empty_logs_execute_is_idempotent)
    check("module delegates cleanup", check_module_delegates_to_maintenance_script)

    if failures:
        for failure in failures:
            print(f"[FAIL] {failure}", file=sys.stderr)
        return 1
    print("[PASS] bounded log cleanup contracts")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
