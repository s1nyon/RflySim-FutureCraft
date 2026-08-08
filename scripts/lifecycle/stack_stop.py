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
from .stack_inspect import WindowsPortsProbe, inspect_stack  # noqa: E402
from .stack_manifest import (  # noqa: E402
    command_line_fingerprint,
    entry_matches_process,
    load_manifest,
    save_manifest,
)


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
            leader_ok = proc is not None and entry_matches_process(entry, proc)
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
            problems.append(f"identity mismatch at pid {entry['pid']} ({entry['role']}) after stop")

    return {
        "problems": problems,
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

    for side, entry in _ordered_entries(manifest):
        table = win_table if side == "windows" else wsl_table
        backend = win_backend if side == "windows" else wsl_backend
        pid = int(entry["pid"])
        pgid = entry.get("pgid")
        snapshot = table.snapshot()
        proc = find_by_pid(snapshot, pid)
        group = find_by_pgid(snapshot, pgid) if (side == "wsl" and pgid is not None) else []

        if side == "wsl" and pgid is not None:
            leader_ok = proc is not None and entry_matches_process(entry, proc)
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

            ok = backend.stop_group(int(pgid), "INT")
            performed.append(_action(entry, side, "INT", "pgid", status="performed" if ok else "failed"))
            if not ok:
                failure_reasons.append(f"INT to PGID {pgid} ({entry['role']}) failed")
            wait(int_wait_s)

            if backend.alive_group(int(pgid)) or find_by_pgid(table.snapshot(), pgid):
                ok = backend.stop_group(int(pgid), "TERM")
                performed.append(_action(entry, side, "TERM", "pgid", status="performed" if ok else "failed"))
                if not ok:
                    failure_reasons.append(f"TERM to PGID {pgid} ({entry['role']}) failed")
            wait(term_wait_s)

            if find_by_pgid(table.snapshot(), pgid):
                ok = backend.stop_group(int(pgid), "KILL")
                performed.append(_action(entry, side, "KILL", "pgid", status="performed" if ok else "failed"))
                if ok:
                    force_reasons.append(
                        f"PGID {pgid} ({entry['role']}) still alive after TERM; force-stopped after verification"
                    )
                else:
                    failure_reasons.append(f"KILL to PGID {pgid} ({entry['role']}) failed")
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
        if not ok:
            failure_reasons.append(f"{graceful} to pid {pid} ({entry['role']}) failed")
        wait(int_wait_s)

        proc = find_by_pid(table.snapshot(), pid)
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
            refused.append(
                {
                    "pid": pid,
                    "role": entry["role"],
                    "reason": "force-stop verification failed after TERM (PID reused or command line changed); refusing to kill",
                }
            )

    final = _final_verification(manifest, win_table, wsl_table)
    clean = not refused and not failure_reasons and final["clean"]
    stack_ownership.record_stop(
        manifest,
        reason=reason,
        clean=clean,
        force_reasons=force_reasons,
        failure_reasons=failure_reasons + final["problems"],
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
        inspection = inspect_stack(
            manifest,
            win_table=win_table,
            wsl_table=wsl_table,
            ports_probe=WindowsPortsProbe(owned_pids),
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
