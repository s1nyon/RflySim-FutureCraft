#!/usr/bin/env python3
"""Exercise the repository simulation CLI and its offline command contracts."""

from __future__ import annotations

import argparse
import json
import os
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path
from typing import Callable


VALIDATORS = {
    "core": [
        "validate_stage6c.ps1",
        "validate_stage6d.ps1",
        "validate_stage7.ps1",
        "validate_stage8.ps1",
    ],
    "lifecycle": ["validate_lifecycle.ps1"],
    "all": [
        "validate_repository.ps1",
        "validate_stage1.ps1",
        "validate_stage2.ps1",
        "validate_stage2_1.ps1",
        "validate_stage3.ps1",
        "validate_stage4.ps1",
        "validate_stage5.ps1",
        "validate_stage5b.ps1",
        "validate_stage5c.ps1",
        "validate_stage5d.ps1",
        "validate_stage5e.ps1",
        "validate_stage6a.ps1",
        "validate_stage6b.ps1",
        "validate_stage6c.ps1",
        "validate_stage6d.ps1",
        "validate_stage7.ps1",
        "validate_stage8.ps1",
        "validate_lifecycle.ps1",
    ],
}


def run_process(
    arguments: list[str], *, cwd: Path, env: dict[str, str] | None = None
) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        arguments,
        cwd=str(cwd),
        env=env,
        capture_output=True,
        encoding="utf-8",
        errors="replace",
        timeout=120,
        check=False,
    )


def run_cli(
    project_root: Path,
    *arguments: str,
    env: dict[str, str] | None = None,
) -> subprocess.CompletedProcess[str]:
    return run_process(
        [
            "powershell.exe",
            "-NoProfile",
            "-ExecutionPolicy",
            "Bypass",
            "-File",
            str(project_root / "sim.ps1"),
            *arguments,
        ],
        cwd=project_root,
        env=env,
    )


def quote_ps(value: Path) -> str:
    return str(value).replace("'", "''")


def write_validator_fixtures(root: Path) -> None:
    scripts = root / "scripts"
    scripts.mkdir(parents=True)
    for name in sorted({name for suite in VALIDATORS.values() for name in suite}):
        (scripts / name).write_text(
            "$ErrorActionPreference = 'Stop'\n"
            f"Add-Content -LiteralPath $env:SIM_CLI_TEST_LOG -Value '{name}'\n"
            f"if ($env:SIM_CLI_FAIL_SCRIPT -eq '{name}') {{\n"
            f"    [Console]::Error.WriteLine('[fixture stderr] {name} failed')\n"
            "    exit 23\n"
            "}\n"
            "exit 0\n",
            encoding="utf-8",
        )
    build_script = scripts / "wsl" / "build_future_aircraft_ws.sh"
    build_script.parent.mkdir(parents=True)
    build_script.write_text("#!/usr/bin/env bash\nexit 0\n", encoding="utf-8")


def write_fake_wsl(bin_dir: Path) -> None:
    bin_dir.mkdir(parents=True)
    (bin_dir / "wsl.cmd").write_text(
        "@echo off\n"
        "echo %*>>\"%SIM_CLI_WSL_LOG%\"\n"
        "echo %* | findstr /C:\"wslpath\" >nul\n"
        "if %errorlevel%==0 (\n"
        "  echo /tmp/fake-project\n"
        "  exit /b 0\n"
        ")\n"
        "exit /b %SIM_CLI_WSL_EXIT%\n",
        encoding="ascii",
    )


def write_nul_distro_wsl(bin_dir: Path) -> None:
    bin_dir.mkdir(parents=True, exist_ok=True)
    (bin_dir / "wsl.cmd").write_text(
        "@echo off\n"
        '"D:\\PX4PSP\\Python38\\python.exe" -c '
        '"import sys; sys.stdout.buffer.write(\'RflySim-20.04\\r\\n\'.encode(\'utf-16le\'))"\n'
        "exit /b %errorlevel%\n",
        encoding="ascii",
    )


def invoke_module(
    module: Path,
    project_root: Path,
    expression: str,
    *,
    fail_script: str = "",
    wsl_exit: int = 0,
) -> tuple[subprocess.CompletedProcess[str], list[str], list[str]]:
    log_path = project_root / "validator.log"
    wsl_log_path = project_root / "wsl.log"
    bin_dir = project_root / "test-bin"
    write_fake_wsl(bin_dir)
    env = os.environ.copy()
    env.update(
        {
            "PATH": f"{bin_dir}{os.pathsep}{env.get('PATH', '')}",
            "SIM_CLI_TEST_LOG": str(log_path),
            "SIM_CLI_FAIL_SCRIPT": fail_script,
            "SIM_CLI_WSL_LOG": str(wsl_log_path),
            "SIM_CLI_WSL_EXIT": str(wsl_exit),
        }
    )
    command = (
        "$ErrorActionPreference='Stop'; "
        f"Import-Module -Force '{quote_ps(module)}'; "
        f"{expression}"
    )
    result = run_process(
        ["powershell.exe", "-NoProfile", "-Command", command],
        cwd=project_root,
        env=env,
    )
    validators = log_path.read_text(encoding="utf-8").splitlines() if log_path.exists() else []
    wsl_calls = wsl_log_path.read_text(encoding="utf-8").splitlines() if wsl_log_path.exists() else []
    return result, validators, wsl_calls


def result_marker(result: subprocess.CompletedProcess[str]) -> int:
    for line in result.stdout.splitlines():
        if line.startswith("__RESULT__="):
            return int(line.partition("=")[2])
    raise AssertionError(f"missing result marker\nstdout:\n{result.stdout}\nstderr:\n{result.stderr}")


def write_stack_manifest(root: Path, stack_id: str, payload: dict[str, object] | str) -> Path:
    manifest = root / "logs" / "live_stack" / stack_id / "stack_manifest.json"
    manifest.parent.mkdir(parents=True, exist_ok=True)
    text = payload if isinstance(payload, str) else json.dumps(payload)
    manifest.write_text(text, encoding="utf-8")
    return manifest


def create_junction(link: Path, target: Path, cwd: Path) -> None:
    result = run_process(
        [
            "powershell.exe",
            "-NoProfile",
            "-Command",
            (
                f"New-Item -ItemType Junction -Path '{quote_ps(link)}' "
                f"-Target '{quote_ps(target)}' -ErrorAction Stop | Out-Null"
            ),
        ],
        cwd=cwd,
    )
    assert result.returncode == 0, result.stderr or result.stdout


def create_file_symlink(link: Path, target: Path, cwd: Path) -> None:
    result = run_process(
        [
            "powershell.exe",
            "-NoProfile",
            "-Command",
            (
                f"New-Item -ItemType SymbolicLink -Path '{quote_ps(link)}' "
                f"-Target '{quote_ps(target)}' -ErrorAction Stop | Out-Null"
            ),
        ],
        cwd=cwd,
    )
    assert result.returncode == 0, result.stderr or result.stdout


def write_lifecycle_wrapper_fixtures(root: Path) -> Path:
    scripts = root / "scripts"
    scripts.mkdir(parents=True, exist_ok=True)
    log_path = root / "wrapper.log"
    wrappers = {
        "live_stack_start.ps1": "SIM_CLI_START_EXIT",
        "live_stack_inspect.ps1": "SIM_CLI_INSPECT_EXIT",
        "end_live_stack.ps1": "SIM_CLI_STOP_EXIT",
    }
    for name, exit_variable in wrappers.items():
        (scripts / name).write_text(
            f"Add-Content -LiteralPath $env:SIM_CLI_WRAPPER_LOG -Value ('{name} ' + ($args -join ' '))\n"
            f"exit [int]$env:{exit_variable}\n",
            encoding="utf-8",
        )
    return log_path


def write_ego_role_fixtures(root: Path, inspect_status: str) -> tuple[Path, Path]:
    scripts = root / "scripts"
    scripts.mkdir(parents=True, exist_ok=True)
    manifest = root / "logs" / "live_stack" / "stack-fixture" / "stack_manifest.json"
    log_path = root / "wrapper.log"

    (scripts / "live_stack_start.ps1").write_text(
        "param([switch]$Execute, [switch]$DryRun)\n"
        "$manifest = Join-Path $env:SIM_CLI_FIXTURE_ROOT "
        "'logs\\live_stack\\stack-fixture\\stack_manifest.json'\n"
        "New-Item -ItemType Directory -Force -Path (Split-Path -Parent $manifest) | Out-Null\n"
        "'{\"schema_version\":2,\"stack_id\":\"stack-fixture\","
        "\"stop\":{\"clean\":false},\"wsl_processes\":[]}' | "
        "Set-Content -LiteralPath $manifest -Encoding UTF8\n"
        "Add-Content -LiteralPath $env:SIM_CLI_WRAPPER_LOG -Value 'start exit=0'\n"
        "exit 0\n",
        encoding="utf-8",
    )
    (scripts / "fixture_fastlio.ps1").write_text(
        "$runDir = Join-Path $env:SIM_CLI_FIXTURE_ROOT 'logs\\stage7_live\\run-fixture'\n"
        "$readiness = Join-Path $runDir 'sensor_readiness.json'\n"
        "$context = Join-Path $env:SIM_CLI_FIXTURE_ROOT 'logs\\stage7_live\\current_run.env'\n"
        "New-Item -ItemType Directory -Force -Path $runDir | Out-Null\n"
        "'{}' | Set-Content -LiteralPath $readiness -Encoding UTF8\n"
        "@(\"STAGE7_RUN_ID=run-fixture\", \"STAGE7_READINESS_REPORT=$readiness\") | "
        "Set-Content -LiteralPath $context -Encoding UTF8\n"
        "Add-Content -LiteralPath $env:SIM_CLI_WRAPPER_LOG -Value 'fastlio exit=0'\n"
        "exit 0\n",
        encoding="utf-8",
    )
    (scripts / "run_live_fastlio_dual.bat").write_text(
        "@echo off\n"
        'powershell.exe -NoProfile -ExecutionPolicy Bypass -File "%~dp0fixture_fastlio.ps1"\n'
        "exit /b %errorlevel%\n",
        encoding="ascii",
    )
    (scripts / "fixture_ego.ps1").write_text(
        "$manifest = Join-Path $env:SIM_CLI_FIXTURE_ROOT "
        "'logs\\live_stack\\stack-fixture\\stack_manifest.json'\n"
        "$payload = Get-Content -LiteralPath $manifest -Raw | ConvertFrom-Json\n"
        "$payload.wsl_processes = @([pscustomobject]@{role='wsl:ego_swarm_session'})\n"
        "$payload | ConvertTo-Json -Depth 10 | Set-Content -LiteralPath $manifest -Encoding UTF8\n"
        "Add-Content -LiteralPath $env:SIM_CLI_WRAPPER_LOG -Value "
        "'ego registered role runner exit=0'\n"
        "exit 0\n",
        encoding="utf-8",
    )
    (scripts / "run_live_ego_swarm_dual.bat").write_text(
        "@echo off\n"
        'powershell.exe -NoProfile -ExecutionPolicy Bypass -File "%~dp0fixture_ego.ps1"\n'
        "exit /b %errorlevel%\n",
        encoding="ascii",
    )
    (scripts / "live_stack_inspect.ps1").write_text(
        "param([string]$Manifest)\n"
        "Add-Content -LiteralPath $env:SIM_CLI_WRAPPER_LOG -Value "
        f"'inspect {inspect_status} exit=0'\n"
        "Write-Output '{\"owned\":[{\"entry\":{\"role\":\"wsl:ego_swarm_session\"},"
        f"\"status\":\"{inspect_status}\"}}]}}'\n"
        "exit 0\n",
        encoding="utf-8",
    )
    return manifest, log_path


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--project-root", required=True, type=Path)
    args = parser.parse_args()
    project_root = args.project_root.resolve()
    module = project_root / "scripts" / "sim_cli.psm1"
    failures: list[str] = []

    def check(name: str, function: Callable[[], None]) -> None:
        try:
            function()
        except (AssertionError, OSError, subprocess.TimeoutExpired) as exc:
            failures.append(f"{name}: {exc}")

    def check_root_contract() -> None:
        doctor = run_cli(project_root, "doctor")
        assert doctor.returncode in (0, 2), doctor.stderr or doctor.stdout
        assert "[doctor]" in doctor.stdout, doctor.stdout
        invalid_suite = run_cli(project_root, "validate", "-Suite", "invalid")
        assert invalid_suite.returncode != 0
        unknown = run_cli(project_root, "unknown-command")
        assert unknown.returncode != 0

    def check_active_manifest_resolution() -> None:
        def assert_resolution_fails(root: Path, expected: str) -> None:
            result, _, _ = invoke_module(
                module,
                root,
                f"Resolve-ActiveStackManifest -ProjectRoot '{quote_ps(root)}'",
            )
            combined = result.stdout + result.stderr
            assert result.returncode != 0, combined or (
                f"resolver accepted invalid direct entry under {root / 'logs' / 'live_stack'}"
            )
            assert expected.lower() in combined.lower(), combined

        with tempfile.TemporaryDirectory(prefix="sim-cli-manifest-none-") as directory:
            root = Path(directory)
            result, _, _ = invoke_module(
                module,
                root,
                (
                    f"$manifest=Resolve-ActiveStackManifest -ProjectRoot '{quote_ps(root)}'; "
                    "if ($null -eq $manifest) { Write-Output '__EMPTY__' } else { Write-Output $manifest.FullName }"
                ),
            )
            assert result.returncode == 0, result.stderr or result.stdout
            assert "__EMPTY__" in result.stdout, result.stdout

        with tempfile.TemporaryDirectory(prefix="sim-cli-manifest-closed-") as directory:
            root = Path(directory)
            write_stack_manifest(
                root,
                "stack-closed",
                {"schema_version": 2, "stack_id": "stack-closed", "stop": {"clean": True}},
            )
            result, _, _ = invoke_module(
                module,
                root,
                (
                    f"$manifest=Resolve-ActiveStackManifest -ProjectRoot '{quote_ps(root)}'; "
                    "if ($null -eq $manifest) { Write-Output '__EMPTY__' } else { Write-Output $manifest.FullName }"
                ),
            )
            assert result.returncode == 0, result.stderr or result.stdout
            assert "__EMPTY__" in result.stdout, result.stdout

        with tempfile.TemporaryDirectory(prefix="sim-cli-manifest-active-") as directory:
            root = Path(directory)
            active = write_stack_manifest(
                root,
                "stack-active",
                {"schema_version": 2, "stack_id": "stack-active", "stop": {"clean": False}},
            )
            result, _, _ = invoke_module(
                module,
                root,
                (
                    f"$manifest=Resolve-ActiveStackManifest -ProjectRoot '{quote_ps(root)}'; "
                    "Write-Output $manifest.FullName"
                ),
            )
            assert result.returncode == 0, result.stderr or result.stdout
            assert str(active).lower() in result.stdout.lower(), result.stdout

        with tempfile.TemporaryDirectory(prefix="sim-cli-manifest-multiple-") as directory:
            root = Path(directory)
            for stack_id in ("stack-active-a", "stack-active-b"):
                write_stack_manifest(
                    root,
                    stack_id,
                    {"schema_version": 2, "stack_id": stack_id, "stop": {"clean": False}},
                )
            result, _, _ = invoke_module(
                module,
                root,
                f"Resolve-ActiveStackManifest -ProjectRoot '{quote_ps(root)}'",
            )
            assert result.returncode != 0, result.stdout
            assert "multiple active stack manifests" in (result.stdout + result.stderr).lower()

        with tempfile.TemporaryDirectory(prefix="sim-cli-manifest-malformed-") as directory:
            root = Path(directory)
            active = write_stack_manifest(
                root,
                "stack-active",
                {"schema_version": 2, "stack_id": "stack-active", "stop": {"clean": False}},
            )
            write_stack_manifest(root, "stack-malformed", "{not-json")
            result, _, _ = invoke_module(
                module,
                root,
                f"Resolve-ActiveStackManifest -ProjectRoot '{quote_ps(root)}'",
            )
            assert result.returncode != 0, result.stdout
            combined = result.stdout + result.stderr
            assert "malformed stack manifest" in combined.lower(), combined
            assert str(active).lower() not in result.stdout.lower(), result.stdout

        with tempfile.TemporaryDirectory(prefix="sim-cli-manifest-schema-") as directory:
            root = Path(directory)
            write_stack_manifest(
                root,
                "stack-wrong-schema",
                {"schema_version": "2", "stack_id": "stack-wrong-schema", "stop": {"clean": False}},
            )
            result, _, _ = invoke_module(
                module,
                root,
                f"Resolve-ActiveStackManifest -ProjectRoot '{quote_ps(root)}'",
            )
            assert result.returncode != 0, result.stdout
            assert "malformed stack manifest" in (result.stdout + result.stderr).lower()

        with tempfile.TemporaryDirectory(prefix="sim-cli-manifest-name-") as directory:
            root = Path(directory)
            write_stack_manifest(
                root,
                "stack-path-name",
                {"schema_version": 2, "stack_id": "stack-other-name", "stop": {"clean": False}},
            )
            assert_resolution_fails(root, "malformed stack manifest")

        with tempfile.TemporaryDirectory(prefix="sim-cli-manifest-direct-file-") as directory:
            root = Path(directory)
            direct_file = root / "logs" / "live_stack" / "unexpected.txt"
            direct_file.parent.mkdir(parents=True)
            direct_file.write_text("unexpected", encoding="utf-8")
            assert_resolution_fails(root, "not a directory")

        with tempfile.TemporaryDirectory(prefix="sim-cli-manifest-missing-file-") as directory:
            root = Path(directory)
            (root / "logs" / "live_stack" / "stack-missing").mkdir(parents=True)
            assert_resolution_fails(root, "missing or not a file")

        with tempfile.TemporaryDirectory(prefix="sim-cli-manifest-directory-") as directory:
            root = Path(directory)
            (root / "logs" / "live_stack" / "stack-directory" / "stack_manifest.json").mkdir(
                parents=True
            )
            assert_resolution_fails(root, "missing or not a file")

        with tempfile.TemporaryDirectory(prefix="sim-cli-manifest-entry-reparse-") as directory:
            root = Path(directory)
            target = root / "redirected-stack"
            target.mkdir()
            (target / "stack_manifest.json").write_text(
                json.dumps(
                    {
                        "schema_version": 2,
                        "stack_id": "stack-linked",
                        "stop": {"clean": False},
                    }
                ),
                encoding="utf-8",
            )
            manifest_root = root / "logs" / "live_stack"
            manifest_root.mkdir(parents=True)
            create_junction(manifest_root / "stack-linked", target, root)
            assert_resolution_fails(root, "reparse")

        with tempfile.TemporaryDirectory(prefix="sim-cli-manifest-file-reparse-") as directory:
            root = Path(directory)
            stack_dir = root / "logs" / "live_stack" / "stack-linked"
            stack_dir.mkdir(parents=True)
            target = stack_dir / "stack_manifest.real.json"
            target.write_text(
                json.dumps(
                    {
                        "schema_version": 2,
                        "stack_id": "stack-linked",
                        "stop": {"clean": False},
                    }
                ),
                encoding="utf-8",
            )
            create_file_symlink(stack_dir / "stack_manifest.json", target, root)
            assert_resolution_fails(root, "reparse")

        with tempfile.TemporaryDirectory(prefix="sim-cli-manifest-file-escape-") as directory:
            root = Path(directory) / "project"
            root.mkdir()
            stack_dir = root / "logs" / "live_stack" / "stack-escape"
            stack_dir.mkdir(parents=True)
            target = Path(directory) / "outside-manifest.json"
            target.write_text(
                json.dumps(
                    {
                        "schema_version": 2,
                        "stack_id": "stack-escape",
                        "stop": {"clean": False},
                    }
                ),
                encoding="utf-8",
            )
            create_file_symlink(stack_dir / "stack_manifest.json", target, root)
            assert_resolution_fails(root, "reparse")

        with tempfile.TemporaryDirectory(prefix="sim-cli-manifest-root-reparse-") as directory:
            root = Path(directory) / "project"
            root.mkdir()
            target = Path(directory) / "outside-live-stack"
            target.mkdir()
            outside_stack = target / "stack-outside"
            outside_stack.mkdir()
            (outside_stack / "stack_manifest.json").write_text(
                json.dumps(
                    {
                        "schema_version": 2,
                        "stack_id": "stack-outside",
                        "stop": {"clean": False},
                    }
                ),
                encoding="utf-8",
            )
            (root / "logs").mkdir()
            create_junction(root / "logs" / "live_stack", target, root)
            assert_resolution_fails(root, "reparse")

        with tempfile.TemporaryDirectory(prefix="sim-cli-project-root-reparse-") as directory:
            target = Path(directory) / "real-project"
            (target / "logs" / "live_stack").mkdir(parents=True)
            root = Path(directory) / "linked-project"
            create_junction(root, target, Path(directory))
            assert_resolution_fails(root, "reparse")

        with tempfile.TemporaryDirectory(prefix="sim-cli-manifest-hidden-") as directory:
            root = Path(directory)
            active = write_stack_manifest(
                root,
                "stack-hidden",
                {"schema_version": 2, "stack_id": "stack-hidden", "stop": {}},
            )
            hidden = run_process(["attrib", "+h", str(active.parent)], cwd=root)
            assert hidden.returncode == 0, hidden.stderr or hidden.stdout
            try:
                result, _, _ = invoke_module(
                    module,
                    root,
                    (
                        f"$manifest=Resolve-ActiveStackManifest -ProjectRoot '{quote_ps(root)}'; "
                        "Write-Output $manifest.FullName"
                    ),
                )
                assert result.returncode == 0, result.stderr or result.stdout
                assert str(active).lower() in result.stdout.lower(), result.stdout
            finally:
                run_process(["attrib", "-h", str(active.parent)], cwd=root)

    def check_stage7_fail_closed_helpers() -> None:
        with tempfile.TemporaryDirectory(prefix="sim-cli-stage7-context-") as directory:
            root = Path(directory)
            context = root / "current_run.env"
            context.write_text("NOT_A_STAGE7_CONTEXT\n", encoding="utf-8")
            expression = (
                "& (Get-Module sim_cli) { param($path) "
                "Get-Stage7RunContext -ContextPath $path } "
                f"'{quote_ps(context)}'"
            )
            result, _, _ = invoke_module(module, root, expression)
            assert result.returncode != 0, result.stdout
            assert "malformed Stage 7 run context" in (result.stdout + result.stderr)

        with tempfile.TemporaryDirectory(prefix="sim-cli-stage7-role-") as directory:
            root = Path(directory)
            manifest = write_stack_manifest(
                root,
                "stack-active",
                {
                    "schema_version": 2,
                    "stack_id": "stack-active",
                    "stop": {"clean": False},
                    "wsl_processes": [{"role": "wsl:ego_swarm_session"}],
                },
            )
            expression = (
                "$found=& (Get-Module sim_cli) { param($path) "
                "Wait-StackManifestRole -ManifestPath $path -Role 'wsl:ego_swarm_session' "
                "-TimeoutSeconds 0 } "
                f"'{quote_ps(manifest)}'; Write-Output \"__RESULT__=$found\""
            )
            result, _, _ = invoke_module(module, root, expression)
            assert result.returncode == 0, result.stderr or result.stdout
            assert "__RESULT__=True" in result.stdout, result.stdout

    def check_dry_run_repository_dispatch() -> None:
        start = run_cli(project_root, "start")
        assert start.returncode == 0, start.stderr or start.stdout
        assert "[DRY-RUN]" in start.stdout, start.stdout
        assert "profile dev" in start.stdout.lower(), start.stdout

        status = run_cli(project_root, "status")
        assert status.returncode == 0, status.stderr or status.stdout

        stop = run_cli(project_root, "stop")
        assert stop.returncode in (0, 2), stop.stderr or stop.stdout
        assert "DryRun" in stop.stdout or "no active stack" in stop.stdout, stop.stdout

        source = module.read_text(encoding="utf-8")
        lowered = source.lower()
        for protected_wrapper in (
            "live_stack_start.ps1",
            "live_stack_inspect.ps1",
            "end_live_stack.ps1",
        ):
            assert protected_wrapper.lower() in lowered, protected_wrapper
        for banned in (
            "wsl --shutdown",
            "pkill -9",
            "taskkill /F",
            "Stop-Process -Force",
        ):
            assert banned.lower() not in lowered, banned

    def check_protected_wrapper_exit_propagation() -> None:
        with tempfile.TemporaryDirectory(prefix="sim-cli-wrapper-start-") as directory:
            root = Path(directory)
            log_path = write_lifecycle_wrapper_fixtures(root)
            env = os.environ.copy()
            env.update(
                {
                    "SIM_CLI_WRAPPER_LOG": str(log_path),
                    "SIM_CLI_START_EXIT": "41",
                    "SIM_CLI_INSPECT_EXIT": "0",
                    "SIM_CLI_STOP_EXIT": "0",
                }
            )
            expression = (
                f"$result=Invoke-SimStart -ProjectRoot '{quote_ps(root)}' -Profile dev -Execute:$false; "
                'Write-Output "__RESULT__=$result"'
            )
            command = (
                "$ErrorActionPreference='Stop'; "
                f"Import-Module -Force '{quote_ps(module)}'; {expression}"
            )
            result = run_process(
                ["powershell.exe", "-NoProfile", "-Command", command], cwd=root, env=env
            )
            assert result.returncode == 0, result.stderr or result.stdout
            assert result_marker(result) == 41, result.stdout
            assert "live stack start" in result.stdout.lower(), result.stdout
            calls = log_path.read_text(encoding="utf-8").splitlines()
            assert calls == ["live_stack_start.ps1 -DryRun"], calls

        with tempfile.TemporaryDirectory(prefix="sim-cli-wrapper-status-") as directory:
            root = Path(directory)
            log_path = write_lifecycle_wrapper_fixtures(root)
            manifest = write_stack_manifest(
                root,
                "stack-active",
                {"schema_version": 2, "stack_id": "stack-active", "stop": {"clean": False}},
            )
            env = os.environ.copy()
            env.update(
                {
                    "SIM_CLI_WRAPPER_LOG": str(log_path),
                    "SIM_CLI_START_EXIT": "0",
                    "SIM_CLI_INSPECT_EXIT": "31",
                    "SIM_CLI_STOP_EXIT": "0",
                }
            )
            expression = (
                f"$result=Invoke-SimStatus -ProjectRoot '{quote_ps(root)}'; "
                'Write-Output "__RESULT__=$result"'
            )
            command = (
                "$ErrorActionPreference='Stop'; "
                f"Import-Module -Force '{quote_ps(module)}'; {expression}"
            )
            result = run_process(
                ["powershell.exe", "-NoProfile", "-Command", command], cwd=root, env=env
            )
            assert result.returncode == 0, result.stderr or result.stdout
            assert result_marker(result) == 31, result.stdout
            calls = log_path.read_text(encoding="utf-8").splitlines()
            assert len(calls) == 1 and calls[0].startswith("live_stack_inspect.ps1 -Manifest "), calls
            assert str(manifest).lower() in calls[0].lower(), calls

        with tempfile.TemporaryDirectory(prefix="sim-cli-wrapper-stop-") as directory:
            root = Path(directory)
            log_path = write_lifecycle_wrapper_fixtures(root)
            manifest = write_stack_manifest(
                root,
                "stack-active",
                {"schema_version": 2, "stack_id": "stack-active", "stop": {"clean": False}},
            )
            env = os.environ.copy()
            env.update(
                {
                    "SIM_CLI_WRAPPER_LOG": str(log_path),
                    "SIM_CLI_START_EXIT": "0",
                    "SIM_CLI_INSPECT_EXIT": "0",
                    "SIM_CLI_STOP_EXIT": "37",
                }
            )
            expression = (
                f"$result=Invoke-SimStop -ProjectRoot '{quote_ps(root)}' -Execute:$false; "
                'Write-Output "__RESULT__=$result"'
            )
            command = (
                "$ErrorActionPreference='Stop'; "
                f"Import-Module -Force '{quote_ps(module)}'; {expression}"
            )
            result = run_process(
                ["powershell.exe", "-NoProfile", "-Command", command], cwd=root, env=env
            )
            assert result.returncode == 0, result.stderr or result.stdout
            assert result_marker(result) == 37, result.stdout
            calls = log_path.read_text(encoding="utf-8").splitlines()
            assert len(calls) == 1 and calls[0].startswith("end_live_stack.ps1 -Manifest "), calls
            assert str(manifest).lower() in calls[0].lower(), calls
            assert calls[0].endswith(" -DryRun"), calls

        with tempfile.TemporaryDirectory(prefix="sim-cli-wrapper-none-") as directory:
            root = Path(directory)
            result, _, _ = invoke_module(
                module,
                root,
                (
                    f"$status=Invoke-SimStatus -ProjectRoot '{quote_ps(root)}'; "
                    f"$stop=Invoke-SimStop -ProjectRoot '{quote_ps(root)}' -Execute:$false; "
                    'Write-Output "__RESULT__=$status,$stop"'
                ),
            )
            assert result.returncode == 0, result.stderr or result.stdout
            assert "__RESULT__=0,0" in result.stdout, result.stdout
            assert result.stdout.lower().count("no active stack") == 2, result.stdout

    def check_dev_start_rejects_immediate_ego_exit() -> None:
        with tempfile.TemporaryDirectory(prefix="sim-cli-ego-exit-") as directory:
            root = Path(directory)
            manifest, log_path = write_ego_role_fixtures(root, "owned_but_exited")
            env = os.environ.copy()
            env.update(
                {
                    "SIM_CLI_FIXTURE_ROOT": str(root),
                    "SIM_CLI_WRAPPER_LOG": str(log_path),
                }
            )
            expression = (
                f"$result=Invoke-SimStart -ProjectRoot '{quote_ps(root)}' "
                "-Profile dev -Execute:$true; "
                'Write-Output "__RESULT__=$result"'
            )
            command = (
                "$ErrorActionPreference='Stop'; "
                f"Import-Module -Force '{quote_ps(module)}'; {expression}"
            )
            result = run_process(
                ["powershell.exe", "-NoProfile", "-Command", command], cwd=root, env=env
            )
            assert result.returncode == 0, result.stderr or result.stdout
            assert result_marker(result) != 0, result.stdout
            assert "stage 7 dual ego-swarm launch" in result.stdout.lower(), result.stdout
            calls = log_path.read_text(encoding="utf-8").splitlines()
            assert calls == [
                "start exit=0",
                "fastlio exit=0",
                "ego registered role runner exit=0",
                "inspect owned_but_exited exit=0",
            ], calls
            payload = json.loads(manifest.read_text(encoding="utf-8-sig"))
            assert payload["wsl_processes"] == [{"role": "wsl:ego_swarm_session"}], payload

    def check_dev_start_accepts_live_ego_role() -> None:
        with tempfile.TemporaryDirectory(prefix="sim-cli-ego-alive-") as directory:
            root = Path(directory)
            _, log_path = write_ego_role_fixtures(root, "owned_and_alive")
            env = os.environ.copy()
            env.update(
                {
                    "SIM_CLI_FIXTURE_ROOT": str(root),
                    "SIM_CLI_WRAPPER_LOG": str(log_path),
                }
            )
            expression = (
                f"$result=Invoke-SimStart -ProjectRoot '{quote_ps(root)}' "
                "-Profile dev -Execute:$true; "
                'Write-Output "__RESULT__=$result"'
            )
            command = (
                "$ErrorActionPreference='Stop'; "
                f"Import-Module -Force '{quote_ps(module)}'; {expression}"
            )
            result = run_process(
                ["powershell.exe", "-NoProfile", "-Command", command], cwd=root, env=env
            )
            assert result.returncode == 0, result.stderr or result.stdout
            assert result_marker(result) == 0, result.stdout
            calls = log_path.read_text(encoding="utf-8").splitlines()
            assert calls == [
                "start exit=0",
                "fastlio exit=0",
                "ego registered role runner exit=0",
                "inspect owned_and_alive exit=0",
            ], calls

    def check_doctor_accepts_nul_terminated_distro_name() -> None:
        with tempfile.TemporaryDirectory(prefix="sim-cli-doctor-") as directory:
            bin_dir = Path(directory)
            write_nul_distro_wsl(bin_dir)
            env = os.environ.copy()
            env["PATH"] = f"{bin_dir}{os.pathsep}{env.get('PATH', '')}"
            result = run_cli(project_root, "doctor", env=env)
            assert result.returncode == 0, result.stderr or result.stdout
            assert "WSL distro is installed: RflySim-20.04" in result.stdout, result.stdout

    def check_validation_mapping() -> None:
        for suite, expected in VALIDATORS.items():
            with tempfile.TemporaryDirectory(prefix=f"sim-cli-{suite}-") as directory:
                root = Path(directory)
                write_validator_fixtures(root)
                result, validators, _ = invoke_module(
                    module,
                    root,
                    (
                        f"$result=Invoke-SimValidation -ProjectRoot '{quote_ps(root)}' "
                        f"-Suite '{suite}'; Write-Output \"__RESULT__=$result\""
                    ),
                )
                assert result.returncode == 0, result.stderr or result.stdout
                assert result_marker(result) == 0, result.stdout
                assert validators == expected, f"{suite}: {validators!r}"

    def check_mission_mapping_and_build() -> None:
        with tempfile.TemporaryDirectory(prefix="sim-cli-mission-") as directory:
            root = Path(directory)
            write_validator_fixtures(root)
            result, validators, wsl_calls = invoke_module(
                module,
                root,
                (
                    f"$result=Invoke-SimValidation -ProjectRoot '{quote_ps(root)}' "
                    "-Suite 'mission'; Write-Output \"__RESULT__=$result\""
                ),
            )
            assert result.returncode == 0, result.stderr or result.stdout
            assert result_marker(result) == 0, result.stdout
            assert validators == ["validate_repository.ps1"], validators
            assert any("wslpath" in call for call in wsl_calls), wsl_calls
            assert any(
                "build_future_aircraft_ws.sh" in call
                and "--pkg" in call
                and "future_aircraft_mission" in call
                for call in wsl_calls
            ), wsl_calls

    def check_fail_fast_exit_propagation() -> None:
        with tempfile.TemporaryDirectory(prefix="sim-cli-fail-fast-") as directory:
            root = Path(directory)
            write_validator_fixtures(root)
            result, validators, _ = invoke_module(
                module,
                root,
                (
                    f"$result=Invoke-SimValidation -ProjectRoot '{quote_ps(root)}' "
                    "-Suite 'core'; Write-Output \"__RESULT__=$result\""
                ),
                fail_script="validate_stage6d.ps1",
            )
            assert result.returncode == 0, result.stderr or result.stdout
            assert result_marker(result) == 23, result.stdout
            assert validators == ["validate_stage6c.ps1", "validate_stage6d.ps1"], validators
            failed_path = str(root / "scripts" / "validate_stage6d.ps1")
            assert failed_path.lower() in (result.stdout + result.stderr).lower()

        with tempfile.TemporaryDirectory(prefix="sim-cli-dispatch-exit-") as directory:
            root = Path(directory)
            write_validator_fixtures(root)
            shutil.copy2(project_root / "sim.ps1", root / "sim.ps1")
            shutil.copy2(module, root / "scripts" / "sim_cli.psm1")
            log_path = root / "dispatcher-validator.log"
            env = os.environ.copy()
            env.update(
                {
                    "SIM_CLI_TEST_LOG": str(log_path),
                    "SIM_CLI_FAIL_SCRIPT": "validate_stage6d.ps1",
                }
            )
            result = run_cli(root, "validate", "-Suite", "core", env=env)
            validators = log_path.read_text(encoding="utf-8").splitlines()
            assert result.returncode == 23, result.stderr or result.stdout
            assert validators == ["validate_stage6c.ps1", "validate_stage6d.ps1"], validators
            failed_path = str(root / "scripts" / "validate_stage6d.ps1")
            assert failed_path.lower() in (result.stdout + result.stderr).lower()

    def check_build_exit_propagation() -> None:
        with tempfile.TemporaryDirectory(prefix="sim-cli-build-") as directory:
            root = Path(directory)
            (root / "scripts" / "wsl").mkdir(parents=True)
            result, _, wsl_calls = invoke_module(
                module,
                root,
                (
                    f"$result=Invoke-SimBuild -ProjectRoot '{quote_ps(root)}'; "
                    "Write-Output \"__RESULT__=$result\""
                ),
                wsl_exit=29,
            )
            assert result.returncode == 0, result.stderr or result.stdout
            assert result_marker(result) == 29, result.stdout
            assert "[build] WSL RflySim-20.04:" in result.stdout, result.stdout
            assert any("build_future_aircraft_ws.sh" in call for call in wsl_calls), wsl_calls

    check("root CLI contract", check_root_contract)
    check("active manifest resolution", check_active_manifest_resolution)
    check("Stage 7 fail-closed helpers", check_stage7_fail_closed_helpers)
    check("dry-run repository dispatch", check_dry_run_repository_dispatch)
    check("protected wrapper exit propagation", check_protected_wrapper_exit_propagation)
    check("dev start rejects immediate EGO exit", check_dev_start_rejects_immediate_ego_exit)
    check("dev start accepts live EGO role", check_dev_start_accepts_live_ego_role)
    check("doctor handles NUL-terminated distro names", check_doctor_accepts_nul_terminated_distro_name)
    check("validation suite mapping", check_validation_mapping)
    check("mission mapping and focused build", check_mission_mapping_and_build)
    check("validation fail-fast propagation", check_fail_fast_exit_propagation)
    check("build exit propagation", check_build_exit_propagation)

    if failures:
        for failure in failures:
            print(f"[FAIL] {failure}", file=sys.stderr)
        return 1
    print("[PASS] simulation CLI contracts")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
