#!/usr/bin/env python3
"""Exercise the repository simulation CLI and its offline command contracts."""

from __future__ import annotations

import argparse
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

    def check_deferred_commands_fail_closed() -> None:
        for command in ("start", "status", "stop", "clean-logs"):
            result = run_cli(project_root, command)
            assert result.returncode != 0, f"{command} unexpectedly succeeded"
            assert "not implemented" in (result.stdout + result.stderr).lower(), (
                f"{command} did not explain its safe refusal"
            )

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
    check("deferred commands fail closed", check_deferred_commands_fail_closed)
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
