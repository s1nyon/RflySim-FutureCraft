"""Graceful stop: manifest-only, PGID-aware, final-verification clean."""

from __future__ import annotations

import json
import subprocess
import sys
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import List, Optional

if __name__ == "__main__" and __package__ is None:
    sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
    from lifecycle import stack_stop as _self

    raise SystemExit(_self._cli_main())

from . import stack_ownership  # noqa: E402
from .process_table import find_by_pgid, find_by_pid  # noqa: E402
from .stack_inspect import WslAwarePortsProbe, inspect_stack  # noqa: E402
from .stack_manifest import (  # noqa: E402
    command_line_fingerprint,
    entry_matches_process,
    load_manifest,
    normalize_command_line,
    parse_utc,
    save_manifest,
)

MATCH_TOLERANCE_SEC = 2.0


@dataclass
class StopAction:
    side: str  # windows | wsl
    pid: int
    pgid: Optional[int]
    target: str  # pid | pgid
    signal: str  # close | INT | TERM | KILL
    role: str
    entry: dict
    status: str = "planned"
    start_time: str = ""
    fingerprint: str = ""
    ownership_reason: str = ""


@dataclass
class StopReport:
    manifest_path: Optional[str] = None
    stack_id: Optional[str] = None
    dry_run: bool = True
    reason: str = ""
    actions: List[StopAction] = field(default_factory=list)
    refused: List[dict] = field(default_factory=list)
    clean: bool = False
    final_verification: dict = field(default_factory=dict)


class StopBackend:
    """Protocol: graceful close, pid/group signals, task deletion."""

    def close_main_window(self, proc) -> bool:
        raise NotImplementedError

    def stop(self, proc, signal: str) -> bool:
        raise NotImplementedError

    def stop_group(self, pgid: int, signal: str) -> bool:
        raise NotImplementedError

    def alive_group(self, pgid: int) -> bool:
        raise NotImplementedError

    def delete_task(self, identity: str) -> bool:
        raise NotImplementedError


class WindowsStopBackend(StopBackend):
    """Windows side: taskkill without /F for graceful close, Stop-Process for TERM/KILL."""

    def __init__(self, powershell: str = "powershell.exe"):
        self.powershell = powershell

    def _run(self, command: List[str]) -> bool:
        try:
            result = subprocess.run(
                command,
                capture_output=True,
                text=True,
                encoding="utf-8",
                errors="replace",
                timeout=30,
            )
            return result.returncode == 0
        except (subprocess.SubprocessError, OSError):
            return False

    def close_main_window(self, proc) -> bool:
        return self._run(["taskkill.exe", "/PID", str(int(proc.pid))])

    def stop(self, proc, signal: str) -> bool:
        pid = str(int(proc.pid))
        if signal == "TERM":
            return self._run([self.powershell, "-NoLogo", "-NoProfile", "-Command",
                              f"Stop-Process -Id {pid} -ErrorAction SilentlyContinue"])
        if signal == "KILL":
            return self._run([self.powershell, "-NoLogo", "-NoProfile", "-Command",
                              f"Stop-Process -Id {pid} -Force -ErrorAction SilentlyContinue"])
        raise ValueError(f"unsupported Windows signal: {signal}")

    def stop_group(self, pgid: int, signal: str) -> bool:
        return False

    def alive_group(self, pgid: int) -> bool:
        return False

    def delete_task(self, identity: str) -> bool:
        return self._run(["schtasks.exe", "/delete", "/tn", identity, "/f"])


class WslStopBackend(StopBackend):
    """WSL side: explicit PID/PGID signals only; never global process-kill, never WSL distribution shutdown."""

    def __init__(self, distro: str = "RflySim-20.04", wsl: str = "wsl.exe"):
        self.distro = distro
        self.wsl = wsl

    def _run(self, bash_command: str) -> bool:
        try:
            result = subprocess.run(
                [self.wsl, "-d", self.distro, "-e", "bash", "-lic", bash_command],
                capture_output=True,
                text=True,
                encoding="utf-8",
                errors="replace",
                timeout=30,
            )
            return result.returncode == 0
        except (subprocess.SubprocessError, OSError):
            return False

    def close_main_window(self, proc) -> bool:
        return False

    def stop(self, proc, signal: str) -> bool:
        if signal not in ("INT", "TERM", "KILL"):
            raise ValueError(f"unsupported WSL signal: {signal}")
        return self._run(f"kill -{signal} -- {int(proc.pid)} 2>/dev/null || true")

    def stop_group(self, pgid: int, signal: str) -> bool:
        if signal not in ("INT", "TERM", "KILL"):
            raise ValueError(f"unsupported WSL signal: {signal}")
        return self._run(f"kill -{signal} -- -{int(pgid)} 2>/dev/null || true")

    def alive_group(self, pgid: int) -> bool:
        return self._run(f"kill -0 -- -{int(pgid)} 2>/dev/null")

    def delete_task(self, identity: str) -> bool:
        return False


class MarkerVerifier:
    """Re-verification hook for spawn_attested entries before any signal."""

    def verify(self, entry: dict, proc) -> bool:
        raise NotImplementedError


class WslMarkerVerifier(MarkerVerifier):
    """Re-checks /proc/<pid>/environ RFLY_STACK_ID for spawn_attested entries."""

    def __init__(self, distro: str = "RflySim-20.04", wsl: str = "wsl.exe"):
        self.distro = distro
        self.wsl = wsl

    def verify(self, entry: dict, proc) -> bool:
        if entry.get("ownership", {}).get("granted") != "spawn_attested":
            return True
        if not entry_matches_process(entry, proc):
            return False
        stack_id = entry.get("ownership", {}).get("stack_marker", {}).get("value")
        if not stack_id:
            return False
        try:
            result = subprocess.run(
                [
                    self.wsl, "-d", self.distro, "-e", "bash", "-lic",
                    f"bash /mnt/d/PX4PSP/RflySimAPIs/8.RflySimVision/3.CustExps/"
                    f"e13.RobotCom26Adv/future_aircraft_sim/scripts/wsl/live_stack_wsl_ops.sh "
                    f"marker {int(proc.pid)} {stack_id}",
                ],
                capture_output=True,
                text=True,
                encoding="utf-8",
                errors="replace",
                timeout=30,
            )
            return result.returncode == 0
        except (subprocess.SubprocessError, OSError):
            return False


WSL_SESSION_ROLE_FRAGMENTS = {
    "wsl:px4_build_session": ("sitl_multiple_run_rfly.sh", "tail -f /dev/null"),
    "wsl:stage2_launcher": ("stage2_two_mavros.sh",),
    "wsl:roscore": ("roscore",),
    "wsl:mavros_uav1": ("roslaunch", "mavros"),
    "wsl:mavros_uav2": ("roslaunch", "mavros"),
    "wsl:px4_mavlink_uav1": ("px4-mavlink",),
    "wsl:px4_mavlink_uav2": ("px4-mavlink",),
    "wsl:rviz_session": ("rflysim_rviz.launch",),
}


def wsl_session_argv_verified(entry: dict, proc) -> bool:
    """Narrow identity relaxation for WSL launcher sessions whose argv
    legitimately transforms after registration (same PID, argv replaced by the
    exec chain, e.g. bash -> roscore/roslaunch or the injected keepalive).

    Accepts only known launcher roles where role + PID + start-time match AND
    the current argv contains a fragment specific to that component. This does
    NOT apply to spawn_attested PX4 entries and does NOT relax inspect's stale
    detection (which still uses entry_matches_process).
    """
    fragments = WSL_SESSION_ROLE_FRAGMENTS.get(str(entry.get("role", "")))
    if fragments is None:
        return False
    if int(entry["pid"]) != int(getattr(proc, "pid", -1)):
        return False
    cmd = normalize_command_line(getattr(proc, "command_line", ""))
    if not any(fragment in cmd for fragment in fragments):
        return False
    entry_time = parse_utc(entry.get("start_time_utc", ""))
    proc_time = parse_utc(getattr(proc, "start_time_utc", ""))
    if entry_time is None or proc_time is None:
        return False
    return abs((entry_time - proc_time).total_seconds()) <= MATCH_TOLERANCE_SEC


def _identity_verified(entry: dict, proc) -> bool:
    return entry_matches_process(entry, proc) or wsl_session_argv_verified(entry, proc)


def _ordered_entries(manifest: dict):
    for entry in manifest["windows_processes"]:
        yield "windows", entry
    for entry in manifest["wsl_processes"]:
        yield "wsl", entry


def _action(entry: dict, side: str, signal: str, target: str, status: str = "planned") -> StopAction:
    return StopAction(
        side=side,
        pid=int(entry["pid"]),
        pgid=entry.get("pgid"),
        target=target,
        signal=signal,
        role=entry["role"],
        entry=entry,
        status=status,
        start_time=entry.get("start_time_utc", ""),
        fingerprint=command_line_fingerprint(entry.get("command_line", "")),
        ownership_reason=entry.get("ownership", {}).get("reason", ""),
    )


def plan_stop(manifest: dict, win_table, wsl_table) -> tuple:
    actions: List[StopAction] = []
    refused: List[dict] = []
    for side, entry in _ordered_entries(manifest):
        table = win_table if side == "windows" else wsl_table
        snapshot = table.snapshot()
        proc = find_by_pid(snapshot, entry["pid"])
        pgid = entry.get("pgid")

        if side == "wsl" and pgid is not None:
            group = find_by_pgid(snapshot, pgid)
            leader_ok = proc is not None and _identity_verified(entry, proc)
            if not group and proc is None:
                actions.append(_action(entry, side, "INT", "pgid", status="already_exited"))
                continue
            if not group and proc is not None and not leader_ok:
                refused.append(
                    {
                        "pid": int(entry["pid"]),
                        "pgid": int(pgid),
                        "role": entry["role"],
                        "reason": "PID/start-time/command-line verification failed and PGID group is gone (PID reuse)",
                    }
                )
                continue
            for signal in ("INT", "TERM", "KILL"):
                actions.append(_action(entry, side, signal, "pgid"))
            continue

        if proc is None:
            actions.append(_action(entry, side, "close" if side == "windows" else "INT", "pid", status="already_exited"))
            continue
        if not entry_matches_process(entry, proc):
            refused.append(
                {
                    "pid": int(entry["pid"]),
                    "role": entry["role"],
                    "reason": "PID/start-time/command-line verification failed (possible PID reuse)",
                }
            )
            continue
        graceful = "close" if side == "windows" else "INT"
        for signal in (graceful, "TERM", "KILL"):
            actions.append(_action(entry, side, signal, "pid"))
    return actions, refused


def _final_verification(manifest: dict, win_table, wsl_table) -> dict:
    """Post-stop truth: owned alive=0, no orphans, no stale/identity mismatch."""
    win_snapshot = win_table.snapshot()
    wsl_snapshot = wsl_table.snapshot()
    problems: List[str] = []
    recycled: List[int] = []

    for side, entry in _ordered_entries(manifest):
        snapshot = win_snapshot if side == "windows" else wsl_snapshot
        proc = find_by_pid(snapshot, entry["pid"])
        pgid = entry.get("pgid")
        if side == "wsl" and pgid is not None:
            group = find_by_pgid(snapshot, pgid)
            if group:
                problems.append(
                    f"owned PGID {pgid} ({entry['role']}) still has {len(group)} process(es) after stop"
                )
                continue
            if proc is not None and entry_matches_process(entry, proc):
                problems.append(f"owned pid {entry['pid']} ({entry['role']}) still alive after stop")
            elif proc is not None:
                problems.append(f"identity mismatch at pid {entry['pid']} ({entry['role']}) after stop")
            continue
        if proc is not None and entry_matches_process(entry, proc):
            problems.append(f"owned pid {entry['pid']} ({entry['role']}) still alive after stop")
        elif proc is not None:
            # PID was recycled by an unrelated process -> the original owned
            # process is verifiably gone. Not a stop failure; the stale entry is
            # retired by execute_stop after a clean verification.
            recycled.append(int(entry["pid"]))

    return {
        "problems": problems,
        "recycled_pids": recycled,
        "clean": len(problems) == 0,
        "checked_at_utc": stack_ownership.utc_now_iso(),
    }


def execute_stop(
    manifest: dict,
    win_table,
    wsl_table,
    win_backend: StopBackend,
    wsl_backend: StopBackend,
    dry_run: bool = True,
    reason: str = "",
    int_wait_s: float = 5.0,
    term_wait_s: float = 5.0,
    wait_fn=None,
    attest_verifier: Optional[MarkerVerifier] = None,
) -> StopReport:
    wait = wait_fn or time.sleep
    planned, refused = plan_stop(manifest, win_table, wsl_table)
    if dry_run:
        return StopReport(
            stack_id=manifest.get("stack_id"),
            dry_run=True,
            reason=reason,
            actions=planned,
            refused=refused,
            clean=not refused,
        )

    performed: List[StopAction] = []
    force_reasons: List[str] = []
    failure_reasons: List[str] = []
    recycled_after_term: List[int] = []

    for side, entry in _ordered_entries(manifest):
        table = win_table if side == "windows" else wsl_table
        backend = win_backend if side == "windows" else wsl_backend
        pid = int(entry["pid"])
        pgid = entry.get("pgid")
        snapshot = table.snapshot()
        proc = find_by_pid(snapshot, pid)
        group = find_by_pgid(snapshot, pgid) if (side == "wsl" and pgid is not None) else []

        if side == "wsl" and pgid is not None:
            leader_ok = proc is not None and _identity_verified(entry, proc)
            if not group and proc is None:
                performed.append(_action(entry, side, "INT", "pgid", status="already_exited"))
                continue
            if not group and proc is not None and not leader_ok:
                refused.append(
                    {
                        "pid": pid,
                        "pgid": int(pgid),
                        "role": entry["role"],
                        "reason": "verification failed and PGID group is gone (PID reuse)",
                    }
                )
                continue

            # spawn_attested marker re-verification (leader, or an owned group member).
            if entry.get("ownership", {}).get("granted") == "spawn_attested" and attest_verifier is not None:
                verify_proc = proc if leader_ok else (group[0] if group else None)
                if verify_proc is None or not attest_verifier.verify(entry, verify_proc):
                    refused.append(
                        {
                            "pid": pid,
                            "role": entry["role"],
                            "reason": "spawn_attested marker/identity re-verification failed before stop",
                        }
                    )
                    continue

            owned_entries = {int(e["pid"]): e for e in manifest["wsl_processes"]}

            def member_verified(member) -> bool:
                member_entry = owned_entries.get(int(member.pid))
                if member_entry is None or not _identity_verified(member_entry, member):
                    return False
                if member_entry.get("ownership", {}).get("granted") == "spawn_attested" and attest_verifier is not None:
                    return attest_verifier.verify(member_entry, member)
                return True

            unowned_members = [m for m in group if int(m.pid) not in owned_entries]
            use_group = bool(group) and not unowned_members and all(member_verified(m) for m in group)

            for signal in ("INT", "TERM", "KILL"):
                snapshot = table.snapshot()
                group = find_by_pgid(snapshot, pgid) if pgid is not None else []
                if not group and not find_by_pid(snapshot, pid):
                    break
                if use_group and group:
                    ok = backend.stop_group(int(pgid), signal)
                    performed.append(
                        _action(entry, side, signal, "pgid", status="performed" if ok else "failed")
                    )
                    if not ok:
                        failure_reasons.append(f"{signal} to PGID {pgid} ({entry['role']}) failed")
                else:
                    targets = [
                        m for m in group if int(m.pid) in owned_entries and member_verified(m)
                    ]
                    for member in targets:
                        ok = backend.stop(member, signal)
                        performed.append(
                            _action(entry, side, signal, "pid", status="performed" if ok else "failed")
                        )
                        if not ok:
                            failure_reasons.append(
                                f"{signal} to pid {int(member.pid)} ({entry['role']}) failed"
                            )
                        elif signal == "KILL":
                            force_reasons.append(
                                f"pid {int(member.pid)} ({entry['role']}) still alive after TERM; "
                                "force-stopped after re-verification"
                            )
                if signal == "INT":
                    wait(int_wait_s)
                elif signal == "TERM":
                    wait(term_wait_s)
            continue

        if proc is None:
            performed.append(_action(entry, side, "close" if side == "windows" else "INT", "pid", status="already_exited"))
            continue
        if not entry_matches_process(entry, proc):
            refused.append(
                {
                    "pid": pid,
                    "role": entry["role"],
                    "reason": "PID/start-time/command-line verification failed (possible PID reuse)",
                }
            )
            continue

        graceful = "close" if side == "windows" else "INT"
        ok = backend.close_main_window(proc) if graceful == "close" else backend.stop(proc, graceful)
        performed.append(_action(entry, side, graceful, "pid", status="performed" if ok else "failed"))
        wait(int_wait_s)

        proc = find_by_pid(table.snapshot(), pid)
        # NOTE: a failed graceful close (taskkill /PID without /F is rejected by
        # windowless/console GUI processes) is NOT recorded as a hard failure.
        # The authoritative end state is final verification; TERM/KILL failures
        # are still recorded below when the process actually survives.
        if proc is not None and entry_matches_process(entry, proc):
            ok = backend.stop(proc, "TERM")
            performed.append(_action(entry, side, "TERM", "pid", status="performed" if ok else "failed"))
            if not ok:
                failure_reasons.append(f"TERM to pid {pid} ({entry['role']}) failed")
        wait(term_wait_s)

        proc = find_by_pid(table.snapshot(), pid)
        if proc is None:
            continue
        if entry_matches_process(entry, proc):
            ok = backend.stop(proc, "KILL")
            performed.append(_action(entry, side, "KILL", "pid", status="performed" if ok else "failed"))
            if ok:
                force_reasons.append(
                    f"pid {pid} ({entry['role']}) still alive after TERM; force-stopped after verification"
                )
            else:
                failure_reasons.append(f"KILL to pid {pid} ({entry['role']}) failed")
        else:
            # PID was recycled between TERM and KILL: the original owned process
            # is verifiably gone. Never kill the new occupant; retire the stale
            # entry after final verification instead of failing the closure.
            recycled_after_term.append(pid)

    final = _final_verification(manifest, win_table, wsl_table)
    clean = not refused and not failure_reasons and final["clean"]
    retired_stale = list(dict.fromkeys(final.get("recycled_pids", []) + recycled_after_term))
    if clean and retired_stale:
        recycled_set = set(retired_stale)
        manifest["windows_processes"] = [
            e for e in manifest["windows_processes"] if int(e["pid"]) not in recycled_set
        ]
        manifest["wsl_processes"] = [
            e for e in manifest["wsl_processes"] if int(e["pid"]) not in recycled_set
        ]
    stack_ownership.record_stop(
        manifest,
        reason=reason,
        clean=clean,
        force_reasons=force_reasons,
        failure_reasons=failure_reasons + final["problems"],
        retired_stale_entries=retired_stale,
    )
    if clean and manifest.get("launcher", {}).get("kind") == "scheduled_task":
        identity = manifest["launcher"].get("identity")
        if identity:
            win_backend.delete_task(identity)
    return StopReport(
        stack_id=manifest.get("stack_id"),
        dry_run=False,
        reason=reason,
        actions=performed,
        refused=refused,
        clean=clean,
        final_verification=final,
    )


def report_to_dict(report: StopReport) -> dict:
    return {
        "stack_id": report.stack_id,
        "dry_run": report.dry_run,
        "reason": report.reason,
        "clean": report.clean,
        "final_verification": report.final_verification,
        "actions": [
            {
                "side": a.side,
                "pid": a.pid,
                "pgid": a.pgid,
                "target": a.target,
                "signal": a.signal,
                "role": a.role,
                "status": a.status,
                "start_time": a.start_time,
                "fingerprint": a.fingerprint,
                "ownership_reason": a.ownership_reason,
            }
            for a in report.actions
        ],
        "refused": report.refused,
    }


def _cli_main() -> int:
    import argparse

    from .process_table import WindowsProcessTable, WslProcessTable
    from .stack_inspect import report_to_dict as inspect_to_dict

    parser = argparse.ArgumentParser()
    parser.add_argument("--manifest", required=True, type=Path)
    parser.add_argument("--distro", default="RflySim-20.04")
    parser.add_argument("--execute", action="store_true", help="required for real stop; default is DryRun")
    parser.add_argument("--reason", default="")
    parser.add_argument("--int-wait", type=float, default=5.0)
    parser.add_argument("--term-wait", type=float, default=5.0)
    args = parser.parse_args()

    manifest = load_manifest(args.manifest)
    win_table = WindowsProcessTable()
    wsl_table = WslProcessTable(args.distro)
    dry_run = not args.execute

    if not dry_run:
        owned_pids = [int(e["pid"]) for e in manifest["windows_processes"]]
        owned_wsl_pids = [int(e["pid"]) for e in manifest["wsl_processes"]]
        inspection = inspect_stack(
            manifest,
            win_table=win_table,
            wsl_table=wsl_table,
            ports_probe=WslAwarePortsProbe(owned_pids, owned_wsl_pids, args.distro),
            ros_probe=None,
        )
        if inspection.fail_closed:
            print(json.dumps(inspect_to_dict(inspection), indent=2, ensure_ascii=False))
            print("[stop] ABORT: inspect fail-closed (unknown/stale/port conflict); refusing to stop", file=sys.stderr)
            return 2

    report = execute_stop(
        manifest,
        win_table=win_table,
        wsl_table=wsl_table,
        win_backend=WindowsStopBackend(),
        wsl_backend=WslStopBackend(args.distro),
        dry_run=dry_run,
        reason=args.reason,
        int_wait_s=args.int_wait,
        term_wait_s=args.term_wait,
        attest_verifier=WslMarkerVerifier(args.distro) if not dry_run else None,
    )
    if not dry_run:
        save_manifest(manifest, args.manifest)
    print(json.dumps(report_to_dict(report), indent=2, ensure_ascii=False))
    if report.clean:
        print("[stop] clean")
        return 0
    print("[stop] NOT clean; see refused/actions/final_verification", file=sys.stderr)
    return 1


if __name__ == "__main__":
    raise SystemExit(_cli_main())
