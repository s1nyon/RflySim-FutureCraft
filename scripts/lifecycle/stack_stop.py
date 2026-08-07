"""Graceful stop orchestrator: manifest-owned processes only, verified force as last resort."""

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

from .process_table import find_by_pid
from .stack_manifest import entry_matches_process, load_manifest, save_manifest
from . import stack_ownership
from .stack_inspect import WindowsPortsProbe, inspect_stack


@dataclass
class StopAction:
    side: str  # windows | wsl
    pid: int
    pgid: Optional[int]
    signal: str  # close | INT | TERM | KILL
    role: str
    entry: dict
    status: str = "planned"


@dataclass
class StopReport:
    manifest_path: Optional[str] = None
    stack_id: Optional[str] = None
    dry_run: bool = True
    reason: str = ""
    actions: List[StopAction] = field(default_factory=list)
    refused: List[dict] = field(default_factory=list)
    clean: bool = False


class StopBackend:
    """Protocol: graceful close, signal stop, task deletion."""

    def close_main_window(self, proc) -> bool:
        raise NotImplementedError

    def stop(self, proc, signal: str) -> bool:
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

    def delete_task(self, identity: str) -> bool:
        return self._run(["schtasks.exe", "/delete", "/tn", identity, "/f"])


class WslStopBackend(StopBackend):
    """WSL side: explicit-PID kill only; never global process-kill, never WSL distribution shutdown."""

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
        pid = str(int(proc.pid))
        return self._run(f"kill -{signal} -- {pid} 2>/dev/null || true")

    def delete_task(self, identity: str) -> bool:
        return False


def _ordered_entries(manifest: dict):
    for entry in manifest["windows_processes"]:
        yield "windows", entry
    for entry in manifest["wsl_processes"]:
        yield "wsl", entry


def plan_stop(manifest: dict, win_table, wsl_table) -> tuple:
    actions: List[StopAction] = []
    refused: List[dict] = []
    for side, entry in _ordered_entries(manifest):
        table = win_table if side == "windows" else wsl_table
        proc = find_by_pid(table.snapshot(), entry["pid"])
        if proc is None:
            actions.append(
                StopAction(side, int(entry["pid"]), entry.get("pgid"), "close" if side == "windows" else "INT",
                           entry["role"], entry, status="already_exited")
            )
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
            actions.append(
                StopAction(side, int(entry["pid"]), entry.get("pgid"), signal,
                           entry["role"], entry, status="planned")
            )
    return actions, refused


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
    for side, entry in _ordered_entries(manifest):
        table = win_table if side == "windows" else wsl_table
        backend = win_backend if side == "windows" else wsl_backend
        pid = int(entry["pid"])

        proc = find_by_pid(table.snapshot(), pid)
        if proc is None:
            performed.append(StopAction(side, pid, entry.get("pgid"), "close" if side == "windows" else "INT",
                                        entry["role"], entry, status="already_exited"))
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

        # Phase 1: graceful close
        graceful = "close" if side == "windows" else "INT"
        ok = backend.close_main_window(proc) if graceful == "close" else backend.stop(proc, graceful)
        performed.append(StopAction(side, pid, entry.get("pgid"), graceful, entry["role"], entry,
                                    status="performed" if ok else "failed"))
        wait(int_wait_s)

        # Phase 2: SIGTERM
        proc = find_by_pid(table.snapshot(), pid)
        if proc is not None and entry_matches_process(entry, proc):
            ok = backend.stop(proc, "TERM")
            performed.append(StopAction(side, pid, entry.get("pgid"), "TERM", entry["role"], entry,
                                        status="performed" if ok else "failed"))
        wait(term_wait_s)

        # Phase 3: verified force (last resort)
        proc = find_by_pid(table.snapshot(), pid)
        if proc is None:
            continue
        if entry_matches_process(entry, proc):
            ok = backend.stop(proc, "KILL")
            performed.append(StopAction(side, pid, entry.get("pgid"), "KILL", entry["role"], entry,
                                        status="performed" if ok else "failed"))
            if ok:
                force_reasons.append(f"pid {pid} ({entry['role']}) still alive after TERM; force-stopped after verification")
        else:
            refused.append(
                {
                    "pid": pid,
                    "role": entry["role"],
                    "reason": "force-stop verification failed after TERM (PID reused or command line changed); refusing to kill",
                }
            )

    clean = not refused
    stack_ownership.record_stop(manifest, reason=reason, clean=clean, force_reasons=force_reasons)
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
    )


def report_to_dict(report: StopReport) -> dict:
    return {
        "stack_id": report.stack_id,
        "dry_run": report.dry_run,
        "reason": report.reason,
        "clean": report.clean,
        "actions": [
            {
                "side": a.side,
                "pid": a.pid,
                "pgid": a.pgid,
                "signal": a.signal,
                "role": a.role,
                "status": a.status,
            }
            for a in report.actions
        ],
        "refused": report.refused,
    }


def _cli_main() -> int:
    import argparse

    from .process_table import WindowsProcessTable, WslProcessTable

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
            from .stack_inspect import report_to_dict as inspect_to_dict

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
    print("[stop] NOT clean; see refused/actions", file=sys.stderr)
    return 1


if __name__ == "__main__":
    raise SystemExit(_cli_main())
