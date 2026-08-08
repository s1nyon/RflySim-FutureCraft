#!/usr/bin/env python3
"""Static safety contract: banned kill patterns, no scanning-based ownership, registration wiring, health per-status files."""

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
    "GUI_READY", "ROSCORE_READY", "MAVROS_UAV1_CONNECTED", "MAVROS_UAV2_CONNECTED", "COURSE_READY",
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
    if b"\r\n" in path.read_bytes():
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
                (
                    path.name == "validate_stage2.ps1"
                    and label in ("wsl --shutdown", "taskkill /F")
                    and "contractErrors" in text
                )
                or (
                    # start_rflysim_sitl_two.bat contains these only as REMOVAL
                    # targets in the generated-wrapper transform.
                    path.name in ("start_rflysim_sitl_two.bat", "generate_sitl_wrapper.ps1")
                    and label == "taskkill /F"
                    and "name-based kill removed" in text
                )
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

    # 1. Scanning-based ownership is forbidden: stack_record.py must not exist.
    if (project_root / "scripts" / "lifecycle" / "stack_record.py").exists():
        errors.append("scripts/lifecycle/stack_record.py must be removed (scanning-based ownership)")
    for path in py_files:
        text = path.read_text(encoding="utf-8", errors="replace")
        for banned in ("record_windows_processes", "record_wsl_processes", "--adopt-existing", "adopt_existing"):
            if banned in text:
                errors.append(f"{path.relative_to(project_root)} contains banned ownership fallback: {banned}")

    # 2. Hazard stubs remain fail-fast and dangerous-free.
    for name in ("cleanup_sim_stack.ps1", "restart_live_stack.ps1"):
        stub = project_root / "scripts" / name
        if not stub.exists():
            errors.append(f"missing hazard stub: scripts/{name}")
            continue
        text = stub.read_text(encoding="utf-8", errors="replace")
        if "HAZARD-DISABLED" not in text or "exit 1" not in text:
            errors.append(f"{name} must be a fail-fast HAZARD-DISABLED stub")
        for pattern, label in BANNED_PATTERNS:
            if pattern.search(text):
                errors.append(f"{name} must not contain {label}")

    # 3. WSL ops helper: explicit PID/PGID only; group kill pattern required.
    wsl_ops = project_root / "scripts" / "wsl" / "live_stack_wsl_ops.sh"
    if not wsl_ops.exists():
        errors.append("missing scripts/wsl/live_stack_wsl_ops.sh")
    else:
        text = wsl_ops.read_text(encoding="utf-8", errors="replace")
        for pattern, label in BANNED_PATTERNS:
            if pattern.search(text):
                errors.append(f"live_stack_wsl_ops.sh contains banned {label}")
        if 'kill -"$sig" -- "-$pgid"' not in text:
            errors.append("live_stack_wsl_ops.sh must support explicit PGID group kill: kill -$sig -- -$pgid")
        check_lf(wsl_ops, errors)

    # 4. Registration-at-creation wiring in WSL launchers.
    common = project_root / "scripts" / "wsl" / "lifecycle_common.sh"
    if not common.exists():
        errors.append("missing scripts/wsl/lifecycle_common.sh")
    else:
        common_text = common.read_text(encoding="utf-8", errors="replace")
        if "stack_register.py" not in common_text or "STACK_MANIFEST" not in common_text:
            errors.append("lifecycle_common.sh must provide stack_register.py + STACK_MANIFEST handling")
        check_lf(common, errors)
    for sh in ("stage2_two_mavros.sh", "stage7_live_fastlio_dual.sh", "stage7_live_ego_swarm_dual.sh",
               "stage7_live_slam_ego_swarm_flight.sh", "stage8_chain_recorder_once.sh"):
        path = project_root / "scripts" / "wsl" / sh
        if not path.exists():
            errors.append(f"missing scripts/wsl/{sh}")
            continue
        text = path.read_text(encoding="utf-8", errors="replace")
        if "lifecycle_common.sh" not in text:
            errors.append(f"scripts/wsl/{sh} must source lifecycle_common.sh")
        if "stack_register " not in text:
            errors.append(f"scripts/wsl/{sh} must register created processes via stack_register()")
        check_lf(path, errors)

    # 5. Health wiring: per-status producer files; inherited STACK context must survive in the MAVROS launcher.
    stage2_sh = project_root / "scripts" / "wsl" / "stage2_two_mavros.sh"
    stage2_health_sh = project_root / "scripts" / "wsl" / "stage2_health_check.sh"
    start_wsl_bat = project_root / "scripts" / "start_wsl_mavros_two.bat"
    start_course_bat = project_root / "scripts" / "start_predicted_course_two_uav.bat"
    for path, needles in (
        (stage2_sh, ("STACK_HEALTH_DIR", "health_probe.py", "setsid")),
        (stage2_health_sh, ("health_probe.py", "--wait-seconds")),
        (start_wsl_bat, ("STACK_HEALTH_DIR", "stage2_health_check.sh", "--manifest")),
        (start_course_bat, ("STACK_HEALTH_DIR", "GUI_READY", "COURSE_READY", "--manifest")),
    ):
        if not path.exists():
            errors.append(f"missing {path.relative_to(project_root)}")
            continue
        text = path.read_text(encoding="utf-8", errors="replace")
        for needle in needles:
            if needle not in text:
                errors.append(f"{path.relative_to(project_root)} missing wiring: {needle}")
        if path.suffix == ".sh":
            check_lf(path, errors)

    # start_wsl_mavros_two.bat must NOT wipe inherited STACK_ID / STACK_HEALTH_DIR / STACK_MANIFEST.
    if start_wsl_bat.exists():
        text = start_wsl_bat.read_text(encoding="utf-8", errors="replace")
        for wiped in ("set STACK_ID=", "set STACK_HEALTH_DIR=", "set STACK_MANIFEST="):
            if wiped in text:
                errors.append(f"start_wsl_mavros_two.bat must not wipe inherited {wiped.strip()}")

    # 6. Lifecycle entries exist and no shared health.json producer.
    for name in ("live_stack_start.ps1", "live_stack_inspect.ps1", "live_stack_stop.ps1", "live_stack_fresh_instance.ps1"):
        if not (project_root / "scripts" / name).exists():
            errors.append(f"missing {name}")
    live_start_text = (project_root / "scripts" / "live_stack_start.ps1").read_text(encoding="utf-8", errors="replace")
    if "stack_record.py" in live_start_text:
        errors.append("live_stack_start.ps1 must not call scanning-based stack_record.py")
    if "stack_register.py" not in live_start_text:
        errors.append("live_stack_start.ps1 must use stack_register.py registration")
    health_text = "".join(
        p.read_text(encoding="utf-8", errors="replace")
        for p in (stage2_sh, stage2_health_sh, start_wsl_bat, start_course_bat,
                  project_root / "scripts" / "lifecycle" / "health_gate.py")
        if p.exists()
    )
    for status in HEALTH_STATUSES:
        if status not in health_text:
            errors.append(f"health status {status} not wired in launcher scripts")

    if errors:
        for error in errors:
            print(f"[FAIL] {error}")
        return 1
    print("[PASS] lifecycle banned-command and registration/health static contract PASS")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
