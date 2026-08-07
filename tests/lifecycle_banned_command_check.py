#!/usr/bin/env python3
"""Static safety contract for scripts/: banned kill patterns, hazard stubs, health-gate wiring, LF endings."""

from __future__ import annotations

import argparse
import re
from pathlib import Path

BANNED_PATTERNS = [
    (re.compile(r"wsl(?:\s+|\.exe\s+)--shutdown", re.IGNORECASE), "wsl --shutdown"),
    (re.compile(r"pkill\s+-9", re.IGNORECASE), "pkill -9"),
    (re.compile(r"taskkill\s+/F", re.IGNORECASE), "taskkill /F"),
    (re.compile(r"Stop-Process\s+-\w*Force", re.IGNORECASE), "Stop-Process -Force"),
    (re.compile(r"schtasks\s+/delete", re.IGNORECASE), "schtasks /delete"),
    (
        re.compile(r"Get-Process[^\r\n]*Where-Object[^\r\n]*Stop-Process", re.IGNORECASE),
        "name-scan Stop-Process",
    ),
]

LIFECYCLE_PY_BANNED = [
    (re.compile(r"\bpkill\b", re.IGNORECASE), "pkill"),
    (re.compile(r"wsl(?:\s+|\.exe\s+)--shutdown", re.IGNORECASE), "wsl --shutdown"),
]

HEALTH_STATUSES = [
    "GUI_READY",
    "ROSCORE_READY",
    "MAVROS_UAV1_CONNECTED",
    "MAVROS_UAV2_CONNECTED",
    "COURSE_READY",
]


def collect_files(project_root: Path):
    scripts = project_root / "scripts"
    entry_files = []
    py_files = []
    for path in sorted(scripts.rglob("*")):
        if not path.is_file():
            continue
        suffix = path.suffix.lower()
        if suffix in (".ps1", ".bat", ".sh"):
            entry_files.append(path)
        elif suffix == ".py" and "lifecycle" in path.parts:
            py_files.append(path)
    return entry_files, py_files


def check_lf(path: Path, errors: list) -> None:
    bytes_data = path.read_bytes()
    if b"\r\n" in bytes_data:
        errors.append(f"{path.relative_to(Path.cwd())} must use LF line endings for WSL execution")


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--project-root", required=True, type=Path)
    args = parser.parse_args()
    project_root = args.project_root.resolve()
    errors: list = []

    entry_files, py_files = collect_files(project_root)

    for path in entry_files:
        text = path.read_text(encoding="utf-8", errors="replace")
        for pattern, label in BANNED_PATTERNS:
            if pattern.search(text) and not (
                # validate_stage2.ps1 is a guard: it asserts generated SITL
                # wrappers do NOT contain these strings. It never executes them.
                path.name == "validate_stage2.ps1"
                and label in ("wsl --shutdown", "taskkill /F")
                and "contractErrors" in text
            ):
                errors.append(f"{path.relative_to(project_root)} contains banned {label}")

    for path in py_files:
        text = path.read_text(encoding="utf-8", errors="replace")
        for pattern, label in LIFECYCLE_PY_BANNED:
            if pattern.search(text):
                errors.append(f"{path.relative_to(project_root)} contains banned {label}")
        for line in text.splitlines():
            if "schtasks" in line.lower() and "/delete" in line.lower() and "identity" not in line:
                errors.append(f"{path.relative_to(project_root)} schtasks /delete must be parameterized by manifest identity")

    # Hazard stubs: must be fail-fast and carry zero dangerous code.
    for name in ("cleanup_sim_stack.ps1", "restart_live_stack.ps1"):
        stub = project_root / "scripts" / name
        if not stub.exists():
            errors.append(f"missing hazard stub: scripts/{name}")
            continue
        text = stub.read_text(encoding="utf-8", errors="replace")
        if "HAZARD-DISABLED" not in text:
            errors.append(f"{name} must carry a HAZARD-DISABLED marker")
        if "exit 1" not in text:
            errors.append(f"{name} must exit non-zero")
        for pattern, label in BANNED_PATTERNS:
            if pattern.search(text):
                errors.append(f"{name} must not contain {label}")

    # WSL ops helper: explicit-PID kill only.
    wsl_ops = project_root / "scripts" / "wsl" / "live_stack_wsl_ops.sh"
    if not wsl_ops.exists():
        errors.append("missing scripts/wsl/live_stack_wsl_ops.sh")
    else:
        text = wsl_ops.read_text(encoding="utf-8", errors="replace")
        for pattern, label in BANNED_PATTERNS:
            if pattern.search(text):
                errors.append(f"live_stack_wsl_ops.sh contains banned {label}")
        if re.search(r'kill\s+-\"\$sig\" -- "\$pid"', text) is None:
            errors.append("live_stack_wsl_ops.sh must kill only explicit PIDs via 'kill -$SIG -- <pid>'")
        check_lf(wsl_ops, errors)

    # Session-1 health-gate wiring must exist and expose the fixed status enum.
    stage2_sh = project_root / "scripts" / "wsl" / "stage2_two_mavros.sh"
    stage2_health_sh = project_root / "scripts" / "wsl" / "stage2_health_check.sh"
    start_wsl_bat = project_root / "scripts" / "start_wsl_mavros_two.bat"
    start_course_bat = project_root / "scripts" / "start_predicted_course_two_uav.bat"
    checks = [
        (stage2_sh, ("STACK_HEALTH_DIR", "health_probe.py")),
        (stage2_health_sh, ("health_probe.py", "--wait-seconds")),
        (start_wsl_bat, ("STACK_HEALTH_DIR", "stage2_health_check.sh")),
        (start_course_bat, ("STACK_HEALTH_DIR", "GUI_READY", "COURSE_READY")),
    ]
    for path, needles in checks:
        if not path.exists():
            errors.append(f"missing {path.relative_to(project_root)}")
            continue
        text = path.read_text(encoding="utf-8", errors="replace")
        for needle in needles:
            if needle not in text:
                errors.append(f"{path.relative_to(project_root)} missing health wiring: {needle}")
        if path.suffix == ".sh":
            check_lf(path, errors)

    health_text = "".join(
        p.read_text(encoding="utf-8", errors="replace")
        for p in (
            stage2_sh,
            stage2_health_sh,
            start_wsl_bat,
            start_course_bat,
            project_root / "scripts" / "lifecycle" / "health_gate.py",
        )
        if p.exists()
    )
    for status in HEALTH_STATUSES:
        if status not in health_text:
            errors.append(f"health status {status} not wired in launcher scripts")

    # New lifecycle entry points must exist.
    for name in (
        "live_stack_start.ps1",
        "live_stack_inspect.ps1",
        "live_stack_stop.ps1",
        "live_stack_fresh_instance.ps1",
    ):
        path = project_root / "scripts" / name
        if not path.exists():
            errors.append(f"missing {name}")

    for name in ("stage2_two_mavros.sh",):
        check_lf(project_root / "scripts" / "wsl" / name, errors)

    if errors:
        for error in errors:
            print(f"[FAIL] {error}")
        return 1
    print("[PASS] lifecycle banned-command and health-wiring static contract PASS")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
