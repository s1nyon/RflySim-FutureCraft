"""Read-only stack inspection with fail-closed semantics. Never kills anything."""

from __future__ import annotations

import json
import re
import subprocess
import sys
from dataclasses import dataclass, field
from pathlib import Path
from typing import List, Optional, Sequence

if __name__ == "__main__" and __package__ is None:
    sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
    from lifecycle import stack_inspect as _self

    raise SystemExit(_self._cli_main())

from .process_table import find_by_pgid, find_by_pid
from .stack_manifest import entry_matches_process, load_manifest

WINDOWS_STACK_NAMES = {"RflySim3D", "CopterSim", "QGroundControl"}
WSL_SUSPICIOUS_PATTERNS = [
    re.compile(r"(?:^|[/ ])rflysim", re.IGNORECASE),
    re.compile(r"(?:^|[/ ])mavros", re.IGNORECASE),
    re.compile(r"(?:^|[/ ])px4(?![a-z])", re.IGNORECASE),
    re.compile(r"(?:^|[/ ])roscore(?![a-z])", re.IGNORECASE),
    re.compile(r"sensor_bridge", re.IGNORECASE),
    re.compile(r"ego[_-]swarm", re.IGNORECASE),
    re.compile(r"fastlio", re.IGNORECASE),
    re.compile(r"stage2_two_mavros", re.IGNORECASE),
    re.compile(r"multi_uav_mission", re.IGNORECASE),
    re.compile(r"predicted_narrow_course", re.IGNORECASE),
]

# Required-port owners mapped to the live stack WSL components that legitimately
# bind them. WSL2 localhost-forwarded sockets are reflected to the Windows side
# as a phantom "px4"/relay process that can never match manifest PIDs, so a
# probe-level "unknown owner" is not authoritative when the stack itself proves
# the component is alive.
OWNER_ROLE_PREFIXES = {
    # WSL2 localhost forwarding reflects the PX4 UDP sockets to the Windows
    # side as a phantom "px4" process; the stack's own px4 instance is the
    # legitimate owner.
    "uav1-mavros": ("wsl:mavros_uav1", "wsl:px4_mavlink_uav1", "wsl:px4_uav1"),
    "uav2-mavros": ("wsl:mavros_uav2", "wsl:px4_mavlink_uav2", "wsl:px4_uav2"),
    "ros_master": ("wsl:roscore",),
}


@dataclass
class OwnedStatus:
    entry: dict
    status: str  # owned_and_alive | owned_but_exited | stale_pid_reuse


@dataclass
class PortStatus:
    port: int
    protocol: str
    occupied: bool
    owned: Optional[bool]
    detail: str


@dataclass
class RosStatus:
    roscore_alive: bool = False
    mavros_uav1_connected: bool = False
    mavros_uav2_connected: bool = False
    course_ready: bool = False


@dataclass
class InspectReport:
    manifest_path: Optional[str] = None
    stack_id: Optional[str] = None
    owned: List[OwnedStatus] = field(default_factory=list)
    stale: List[OwnedStatus] = field(default_factory=list)
    orphans: List[OwnedStatus] = field(default_factory=list)
    unknown_suspicious: List = field(default_factory=list)
    ports: List[PortStatus] = field(default_factory=list)
    ros: RosStatus = field(default_factory=RosStatus)
    fail_closed: bool = False


class PortsProbe:
    """Protocol: check(port, protocol) -> PortStatus."""

    def check(self, port: int, protocol: str) -> PortStatus:
        raise NotImplementedError


class RosProbe:
    """Protocol: roscore_alive / mavros_connected(ns) / course_ready."""

    def roscore_alive(self) -> bool:
        raise NotImplementedError

    def mavros_connected(self, ns: str) -> bool:
        raise NotImplementedError

    def course_ready(self) -> bool:
        raise NotImplementedError


def _classify_entries(entries: Sequence[dict], processes: Sequence, side: str = "windows") -> tuple:
    owned: List[OwnedStatus] = []
    stale: List[OwnedStatus] = []
    orphans: List[OwnedStatus] = []
    for entry in entries:
        proc = find_by_pid(processes, entry["pid"])
        pgid = entry.get("pgid")
        if side == "wsl" and pgid is not None:
            group = find_by_pgid(processes, pgid)
            leader_ok = proc is not None and entry_matches_process(entry, proc)
            if leader_ok:
                owned.append(OwnedStatus(entry=entry, status="owned_and_alive"))
            elif group:
                status = OwnedStatus(entry=entry, status="owned_orphan")
                owned.append(status)
                orphans.append(status)
            elif proc is None:
                owned.append(OwnedStatus(entry=entry, status="owned_but_exited"))
            else:
                stale.append(OwnedStatus(entry=entry, status="stale_pid_reuse"))
        else:
            if proc is None:
                owned.append(OwnedStatus(entry=entry, status="owned_but_exited"))
            elif entry_matches_process(entry, proc):
                owned.append(OwnedStatus(entry=entry, status="owned_and_alive"))
            else:
                stale.append(OwnedStatus(entry=entry, status="stale_pid_reuse"))
    return owned, stale, orphans


def _unknown_windows(processes: Sequence, manifest: dict) -> List:
    known_pids = {int(e["pid"]) for e in manifest["windows_processes"]}
    unknown: List = []
    for proc in processes:
        if int(proc.pid) in known_pids:
            continue
        if str(getattr(proc, "name", "")) in WINDOWS_STACK_NAMES:
            unknown.append(proc)
    return unknown


def _unknown_wsl(processes: Sequence, manifest: dict) -> List:
    known_pids = {int(e["pid"]) for e in manifest["wsl_processes"]}
    known_pgids = {int(e["pgid"]) for e in manifest["wsl_processes"] if e.get("pgid")}
    unknown: List = []
    for proc in processes:
        if int(proc.pid) in known_pids:
            continue
        if proc.pgid is not None and int(proc.pgid) in known_pgids:
            continue  # owned via the registered PGID (orphan/child of the group)
        if int(getattr(proc, "parent_pid", 0)) in known_pids:
            continue  # direct child of an owned process (e.g. mavros_node under owned roslaunch)
        command_line = str(getattr(proc, "command_line", "")).lower()
        if any(pattern.search(command_line) for pattern in WSL_SUSPICIOUS_PATTERNS):
            unknown.append(proc)
    return unknown


def inspect_stack(
    manifest: dict,
    win_table,
    wsl_table,
    ports_probe: Optional[PortsProbe] = None,
    ros_probe: Optional[RosProbe] = None,
) -> InspectReport:
    win_procs = win_table.snapshot()
    wsl_procs = wsl_table.snapshot()

    owned: List[OwnedStatus] = []
    stale: List[OwnedStatus] = []
    w_owned, w_stale, _ = _classify_entries(manifest["windows_processes"], win_procs, side="windows")
    s_owned, s_stale, s_orphans = _classify_entries(manifest["wsl_processes"], wsl_procs, side="wsl")
    owned.extend(w_owned)
    owned.extend(s_owned)
    stale.extend(w_stale)
    stale.extend(s_stale)
    orphans = list(s_orphans)

    unknown = _unknown_windows(win_procs, manifest) + _unknown_wsl(wsl_procs, manifest)

    ports: List[PortStatus] = []
    for required in manifest.get("required_ports", []):
        port, protocol = int(required["port"]), str(required["protocol"])
        if ports_probe is None:
            ports.append(PortStatus(port, protocol, occupied=False, owned=None, detail="not probed"))
            continue
        status = ports_probe.check(port, protocol)
        # Semantic attribution: when the required port's owner component is an
        # owned-and-alive stack process, the port belongs to this stack even if
        # the raw probe cannot map the binding PID (WSL2 localhost relay).
        if status.occupied and status.owned is False:
            prefixes = OWNER_ROLE_PREFIXES.get(str(required.get("owner", "")))
            if prefixes and any(
                item.status in ("owned_and_alive", "owned_orphan")
                and str(item.entry.get("role", "")).startswith(prefixes)
                for item in owned
            ):
                status.owned = True
                status.detail += f" | attributed to live stack owner {required.get('owner')}"
        ports.append(status)

    ros = RosStatus()
    if ros_probe is not None:
        ros = RosStatus(
            roscore_alive=bool(ros_probe.roscore_alive()),
            mavros_uav1_connected=bool(ros_probe.mavros_connected("uav1")),
            mavros_uav2_connected=bool(ros_probe.mavros_connected("uav2")),
            course_ready=bool(ros_probe.course_ready()),
        )

    fail_closed = bool(unknown) or bool(stale) or any(
        p.occupied and p.owned is False for p in ports
    )
    return InspectReport(
        stack_id=manifest.get("stack_id"),
        owned=owned,
        stale=stale,
        orphans=orphans,
        unknown_suspicious=unknown,
        ports=ports,
        ros=ros,
        fail_closed=fail_closed,
    )


def _proc_to_dict(proc) -> dict:
    return {
        "pid": int(getattr(proc, "pid")),
        "name": str(getattr(proc, "name", "")),
        "start_time_utc": str(getattr(proc, "start_time_utc", "")),
        "command_line": str(getattr(proc, "command_line", "")),
        "parent_pid": int(getattr(proc, "parent_pid", 0)),
        "pgid": getattr(proc, "pgid", None),
    }


def report_to_dict(report: InspectReport) -> dict:
    return {
        "stack_id": report.stack_id,
        "fail_closed": report.fail_closed,
        "owned": [
            {"entry": item.entry, "status": item.status}
            for item in report.owned
        ],
        "stale": [
            {"entry": item.entry, "status": item.status}
            for item in report.stale
        ],
        "orphans": [
            {"entry": item.entry, "status": item.status}
            for item in report.orphans
        ],
        "unknown_suspicious": [_proc_to_dict(p) for p in report.unknown_suspicious],
        "ports": [
            {
                "port": p.port,
                "protocol": p.protocol,
                "occupied": p.occupied,
                "owned": p.owned,
                "detail": p.detail,
            }
            for p in report.ports
        ],
        "ros": {
            "roscore_alive": report.ros.roscore_alive,
            "mavros_uav1_connected": report.ros.mavros_uav1_connected,
            "mavros_uav2_connected": report.ros.mavros_uav2_connected,
            "course_ready": report.ros.course_ready,
        },
    }


def summarize(report: InspectReport) -> dict:
    counts: dict = {"owned_and_alive": 0, "owned_but_exited": 0, "owned_orphan": 0, "stale_pid_reuse": 0}
    for item in report.owned:
        counts[item.status] = counts.get(item.status, 0) + 1
    for item in report.stale:
        counts["stale_pid_reuse"] = counts.get("stale_pid_reuse", 0) + 1
    return {
        "stack_id": report.stack_id,
        "fail_closed": report.fail_closed,
        **counts,
        "orphans": len(report.orphans),
        "unknown_suspicious": len(report.unknown_suspicious),
        "ports_occupied_by_unknown": sum(1 for p in report.ports if p.occupied and p.owned is False),
    }


class WindowsPortsProbe:
    """Real Windows port probe; owned means the owning PID is in the manifest."""

    def __init__(self, owned_pids: Sequence[int]):
        self.owned_pids = {int(p) for p in owned_pids}

    def check(self, port: int, protocol: str) -> PortStatus:
        if protocol == "tcp":
            script = (
                f"Get-NetTCPConnection -State Listen -LocalPort {int(port)} -ErrorAction SilentlyContinue | "
                "Select-Object -ExpandProperty OwningProcess -Unique | ConvertTo-Json -Compress"
            )
        else:
            script = (
                f"Get-NetUDPEndpoint -LocalPort {int(port)} -ErrorAction SilentlyContinue | "
                "Select-Object -ExpandProperty OwningProcess -Unique | ConvertTo-Json -Compress"
            )
        try:
            result = subprocess.run(
                ["powershell.exe", "-NoLogo", "-NoProfile", "-Command", script],
                capture_output=True,
                text=True,
                encoding="utf-8",
                errors="replace",
                timeout=30,
            )
        except (subprocess.SubprocessError, OSError):
            return PortStatus(int(port), protocol, occupied=False, owned=None, detail="probe failed")
        output = result.stdout.strip()
        if not output or output == "null":
            return PortStatus(int(port), protocol, occupied=False, owned=None, detail="free")
        try:
            pids = json.loads(output)
        except json.JSONDecodeError:
            return PortStatus(int(port), protocol, occupied=False, owned=None, detail="unparseable probe")
        if isinstance(pids, int):
            pids = [pids]
        owned = all(int(p) in self.owned_pids for p in pids)
        return PortStatus(int(port), protocol, occupied=True, owned=owned, detail=f"owning pids: {pids}")


class WslAwarePortsProbe:
    """Windows port probe that additionally attributes WSL-owned bindings.

    MAVROS/PX4 required ports live inside WSL2; the Windows-side probe cannot
    map them to manifest WSL PIDs, so a READY stack would always look
    port-conflicted. Query `ss -tulpn` inside the distro and treat a binding as
    owned when its process PID is in the stack manifest's wsl_processes.
    """

    def __init__(
        self,
        owned_win_pids,
        owned_wsl_pids,
        distro: str = "RflySim-20.04",
    ):
        self.win_probe = WindowsPortsProbe(owned_win_pids)
        self.wsl_pids = {int(p) for p in owned_wsl_pids}
        self.distro = distro

    def check(self, port: int, protocol: str) -> PortStatus:
        status = self.win_probe.check(port, protocol)
        if not (status.occupied and status.owned is False):
            return status
        wsl_pids = self._wsl_binding_pids(port, protocol)
        if wsl_pids:
            if any(int(p) in self.wsl_pids for p in wsl_pids):
                return PortStatus(
                    int(port),
                    protocol,
                    occupied=True,
                    owned=True,
                    detail=f"wsl owners in manifest: {sorted(wsl_pids)}",
                )
            return PortStatus(
                int(port),
                protocol,
                occupied=True,
                owned=False,
                detail=f"wsl owners NOT in manifest: {sorted(wsl_pids)}",
            )
        return status

    def _wsl_binding_pids(self, port: int, protocol: str) -> List[int]:
        try:
            result = subprocess.run(
                [
                    "wsl.exe", "-d", self.distro, "-e", "bash", "-lic",
                    f"ss -tulpn 2>/dev/null || lsof -i -P -n 2>/dev/null",
                ],
                capture_output=True,
                text=True,
                encoding="utf-8",
                errors="replace",
                timeout=30,
            )
        except (subprocess.SubprocessError, OSError):
            return []
        pids: List[int] = []
        needle = f":{int(port)}"
        for line in (result.stdout or "").splitlines():
            if needle not in line:
                continue
            if protocol == "tcp" and "LISTEN" not in line.upper():
                continue
            if protocol == "udp" and "UNCONN" not in line.upper() and "UDP" not in line.upper():
                continue
            for m in re.finditer(r"pid=(\d+)", line):
                try:
                    pids.append(int(m.group(1)))
                except ValueError:
                    continue
        return pids


class WslRosProbe:
    def __init__(self, distro: str = "RflySim-20.04"):
        self.distro = distro

    def _bash(self, command: str) -> bool:
        try:
            result = subprocess.run(
                ["wsl.exe", "-d", self.distro, "-e", "bash", "-lic", command],
                capture_output=True,
                text=True,
                encoding="utf-8",
                errors="replace",
                timeout=30,
            )
            return result.returncode == 0
        except (subprocess.SubprocessError, OSError):
            return False

    def roscore_alive(self) -> bool:
        return self._bash("timeout 5s rostopic list >/dev/null 2>&1")

    def mavros_connected(self, ns: str) -> bool:
        return self._bash(
            f"timeout 5s rostopic echo -n 1 /{ns}/mavros/state 2>/dev/null | grep -q 'connected: True'"
        )

    def course_ready(self) -> bool:
        return self._bash(
            "timeout 5s rostopic info /predicted_narrow_course/global_cloud 2>/dev/null | "
            "grep -q 'Publishers:' && ! timeout 5s rostopic info /predicted_narrow_course/global_cloud 2>/dev/null | "
            "grep -q 'Publishers: None'"
        )


def _cli_main() -> int:
    import argparse

    from .process_table import WindowsProcessTable, WslProcessTable

    parser = argparse.ArgumentParser()
    parser.add_argument("--manifest", required=True, type=Path)
    parser.add_argument("--distro", default="RflySim-20.04")
    args = parser.parse_args()

    manifest = load_manifest(args.manifest)
    owned_pids = [int(e["pid"]) for e in manifest["windows_processes"]]
    report = inspect_stack(
        manifest,
        win_table=WindowsProcessTable(),
        wsl_table=WslProcessTable(args.distro),
        ports_probe=WindowsPortsProbe(owned_pids),
        ros_probe=WslRosProbe(args.distro),
    )
    print(json.dumps(report_to_dict(report), indent=2, ensure_ascii=False))
    print(f"[inspect] {json.dumps(summarize(report), ensure_ascii=False)}", file=sys.stderr)
    if report.fail_closed:
        print("[inspect] FAIL-CLOSED: unknown/stale/port-conflict detected; do not proceed", file=sys.stderr)
        return 2
    return 0


if __name__ == "__main__":
    raise SystemExit(_cli_main())
