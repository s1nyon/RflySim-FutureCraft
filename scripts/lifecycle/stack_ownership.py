"""Ownership recording: Windows process-tree descendants and WSL snapshot roles."""

from __future__ import annotations

import re
from typing import List, Optional, Sequence

from .stack_manifest import utc_now_iso

WINDOWS_STACK_NAMES = {"RflySim3D", "CopterSim", "QGroundControl"}

STAGE_CMD_PATTERNS = (
    "start_predicted_course",
    "start_two_uav",
    "start_rflysim_sitl_two",
    "start_wsl_mavros_two",
    "future_aircraft_stage2",
)

WSL_ROLE_PATTERNS = [
    (r"/bin/roscore|bin/roscore|roscore$", "wsl:roscore"),
    (r"px4-mavlink", "wsl:px4_mavlink"),
    (r"rflysim_mavros_px4\.launch.*uav_namespace:=uav1", "wsl:mavros_uav1"),
    (r"rflysim_mavros_px4\.launch.*uav_namespace:=uav2", "wsl:mavros_uav2"),
    (r"(^|/)px4(\s|$)|bin/px4", "wsl:px4_sitl"),
    (r"rflysim_sensor_bridge\.py", "wsl:sensor_bridge"),
    (r"rflysim_fastlio_dual", "wsl:fastlio"),
    (r"rflysim_ego_swarm_dual", "wsl:ego_swarm"),
    (r"mission_executor\.py", "wsl:mission_executor"),
    (r"(predicted_)?narrow_course_cloud_server\.py", "wsl:course_cloud"),
    (r"stage2_two_mavros\.sh", "wsl:stage2_script"),
]


def set_launcher(
    manifest: dict,
    kind: str,
    identity: Optional[str],
    pid: Optional[int] = None,
    command_line: Optional[str] = None,
) -> None:
    manifest["launcher"] = {
        "kind": kind,
        "identity": identity,
        "pid": pid,
        "command_line": command_line,
    }


def set_ros_master(manifest: dict, uri: str) -> None:
    manifest["ros_master"] = {"uri": uri}
    m = re.fullmatch(r"http://([^:/]+)(?::(\d+))?(?:/.*)?", uri)
    manifest["ros_master"]["host"] = m.group(1) if m else uri
    manifest["ros_master"]["port"] = int(m.group(2)) if m and m.group(2) else 80


def set_simulation_instance_id(manifest: dict, simulation_instance_id: Optional[str]) -> None:
    manifest["simulation_instance_id"] = simulation_instance_id


def record_stop(
    manifest: dict,
    reason: str,
    clean: bool,
    force_reasons: Optional[Sequence[str]] = None,
) -> None:
    manifest["stop"] = {
        "last_stop_reason": reason,
        "last_stop_utc": utc_now_iso(),
        "clean": clean,
        "force_reasons": list(force_reasons or []),
    }


def record_health(manifest: dict, health: dict) -> None:
    manifest["health"] = health


def find_descendants(processes: Sequence, root_pid: int) -> List:
    """Return root + all transitive children by ParentProcessId."""
    by_parent: dict = {}
    for proc in processes:
        by_parent.setdefault(int(getattr(proc, "parent_pid")), []).append(proc)
    result: List = []
    for proc in processes:
        if int(proc.pid) == int(root_pid):
            result.append(proc)
            break
    queue = [root_pid]
    seen = set()
    while queue:
        pid = queue.pop(0)
        if pid in seen:
            continue
        seen.add(pid)
        for proc in by_parent.get(pid, []):
            result.append(proc)
            queue.append(int(proc.pid))
    return result


def guess_windows_role(proc) -> str:
    name = str(getattr(proc, "name", "")).lower()
    if name == "rflysim3d":
        return "gui:RflySim3D"
    if name == "coptersim":
        return "gui:CopterSim"
    if name == "qgroundcontrol":
        return "gui:QGroundControl"
    if name == "cmd.exe":
        command_line = str(getattr(proc, "command_line", ""))
        if any(pattern in command_line.lower() for pattern in STAGE_CMD_PATTERNS):
            return "cmd:stage_orchestrator"
    return "win:other"


def _entry_for_proc(proc, role: str) -> dict:
    entry = {
        "pid": int(proc.pid),
        "name": str(getattr(proc, "name", "")),
        "start_time_utc": str(getattr(proc, "start_time_utc", "")),
        "command_line": str(getattr(proc, "command_line", "")),
        "role": role,
        "verified_at_utc": utc_now_iso(),
    }
    raw = getattr(proc, "start_time_raw", None)
    if raw:
        entry["start_time_raw"] = str(raw)
    pgid = getattr(proc, "pgid", None)
    if pgid is not None:
        entry["pgid"] = int(pgid)
    return entry


def record_windows_processes(
    manifest: dict,
    table,
    launcher_pid: Optional[int] = None,
    min_start_time_utc: Optional[str] = None,
) -> List[dict]:
    processes = table.snapshot()
    if launcher_pid is not None:
        candidates = find_descendants(processes, launcher_pid)
    else:
        candidates = [p for p in processes if str(getattr(p, "name", "")) in WINDOWS_STACK_NAMES]
    if min_start_time_utc:
        from .stack_manifest import parse_utc

        min_time = parse_utc(min_start_time_utc)
        if min_time is not None:
            candidates = [
                p
                for p in candidates
                if (lambda t: t is None or t >= min_time)(parse_utc(getattr(p, "start_time_utc", "")))
            ]
    existing = {int(e["pid"]) for e in manifest["windows_processes"]}
    recorded: List[dict] = []
    for proc in candidates:
        if int(proc.pid) in existing:
            continue
        entry = _entry_for_proc(proc, guess_windows_role(proc))
        manifest["windows_processes"].append(entry)
        existing.add(int(proc.pid))
        recorded.append(entry)
    return recorded


def _wsl_role_for_line(command_line: str) -> Optional[str]:
    for pattern, role in WSL_ROLE_PATTERNS:
        if re.search(pattern, command_line):
            return role
    return None


def record_wsl_processes(manifest: dict, snapshot_lines: Sequence[str]) -> List[dict]:
    from .process_table import parse_wsl_snapshot

    processes = parse_wsl_snapshot("\n".join(snapshot_lines))
    existing = {int(e["pid"]) for e in manifest["wsl_processes"]}
    recorded: List[dict] = []
    for proc in processes:
        role = _wsl_role_for_line(proc.command_line)
        if role is None:
            continue
        if int(proc.pid) in existing:
            continue
        entry = _entry_for_proc(proc, role)
        manifest["wsl_processes"].append(entry)
        existing.add(int(proc.pid))
        recorded.append(entry)
    return recorded
