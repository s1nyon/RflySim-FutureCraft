#!/usr/bin/env python3
"""Launch a Windows process and register its PID in the stack manifest at creation time."""

from __future__ import annotations

import argparse
import shlex
import subprocess
import sys
import time
from pathlib import Path
from typing import List, Optional

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from lifecycle.stack_manifest import (  # noqa: E402
    command_line_fingerprint,
    load_manifest,
    parse_utc,
    save_manifest,
    utc_now_iso,
)
from lifecycle.stack_ownership import register_process  # noqa: E402


def _cim_snapshot(powershell: str = "powershell.exe") -> List[dict]:
    """Read-only process snapshot (parent pid + identity) for attach-child verification."""
    script = (
        "Get-CimInstance Win32_Process | "
        "Select-Object ProcessId,ParentProcessId,Name,CreationDate,ExecutablePath,CommandLine | "
        "ConvertTo-Json -Compress"
    )
    try:
        result = subprocess.run(
            [powershell, "-NoLogo", "-NoProfile", "-Command", script],
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
            timeout=60,
        )
    except (subprocess.SubprocessError, OSError):
        return []
    if result.returncode != 0:
        return []
    import json

    try:
        data = json.loads(result.stdout)
    except json.JSONDecodeError:
        return []
    if isinstance(data, dict):
        data = [data]
    return [item for item in (data or []) if isinstance(item, dict)]


def _cim_to_utc(cim_value) -> Optional[str]:
    if not cim_value:
        return None
    text = str(cim_value).strip()
    try:
        import datetime as dt
        import re

        # WMI CIM datetime: 20260808120003.123456+480
        m = re.fullmatch(r"(\d{4})(\d{2})(\d{2})(\d{2})(\d{2})(\d{2})(?:\.\d+)?([+-]\d{3,4})?", text)
        if m:
            year, month, day, hour, minute, second, offset = m.groups()
            base = dt.datetime(int(year), int(month), int(day), int(hour), int(minute), int(second))
            if offset:
                sign = 1 if offset[0] == "+" else -1
                minutes = sign * (int(offset[1:3]) * 60 + int(offset[3:5]))
                base = base - dt.timedelta(minutes=minutes)
            return base.replace(tzinfo=dt.timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
        # PowerShell JSON /Date(<epoch-ms>)/ form
        m2 = re.fullmatch(r"\\?/Date\((\d+)([+-]\d{4})?\)\\?/", text)
        if m2:
            epoch_ms = int(m2.group(1))
            return dt.datetime.fromtimestamp(epoch_ms / 1000.0, tz=dt.timezone.utc).strftime(
                "%Y-%m-%dT%H:%M:%SZ"
            )
    except (TypeError, ValueError):
        return None
    return None


def attach_children(
    manifest: dict,
    parent_pid: int,
    role_prefix: str,
    exe_fragment: str,
    max_wait_s: float = 20.0,
    interval_s: float = 2.0,
) -> List[dict]:
    """Register children of a provably-owned launcher PID (Windows spawn-attested analog).

    This is NOT name/regex scanning: children are only considered when their
    ParentProcessId equals an entry already owned by the current stack, and the
    candidate must additionally carry structural evidence (start-after-parent,
    executable path fragment, command-line fingerprint).
    """
    parent_entry = None
    for entry in manifest.get("windows_processes", []):
        if int(entry.get("pid", -1)) == int(parent_pid):
            parent_entry = entry
            break
    if parent_entry is None:
        raise ValueError(f"parent pid {parent_pid} is not owned by this stack; refusing to attach children")
    parent_start = parse_utc(parent_entry.get("start_time_utc", ""))

    deadline = time.time() + max_wait_s
    registered: List[dict] = []
    seen_pids = {int(e.get("pid", -1)) for e in manifest.get("windows_processes", [])}
    while time.time() < deadline:
        snapshot = _cim_snapshot()
        for item in snapshot:
            try:
                pid = int(item.get("ProcessId"))
                ppid = int(item.get("ParentProcessId") or 0)
            except (TypeError, ValueError):
                continue
            if pid in seen_pids or ppid != int(parent_pid):
                continue
            exe = str(item.get("ExecutablePath") or "")
            cmdline = str(item.get("CommandLine") or "")
            if not exe and not cmdline:
                continue
            normalized = (exe + " " + cmdline).lower().replace("/", "\\")
            if exe_fragment.lower().replace("/", "\\") not in normalized:
                continue
            start_utc = _cim_to_utc(item.get("CreationDate"))
            if parent_start is not None and start_utc is not None:
                start_dt = parse_utc(start_utc)
                if start_dt is not None and (start_dt - parent_start).total_seconds() < -1.0:
                    continue
            entry = register_process(
                manifest,
                side="windows",
                pid=pid,
                role=f"{role_prefix}/child",
                name=str(item.get("Name") or ""),
                command_line=cmdline or exe,
                start_time_utc=start_utc,
                reason="child of registered launcher pid (attach-children; structural evidence)",
                ownership_extras={
                    "granted": "spawn_attested",
                    "ownership_parent_role": parent_entry.get("role", role_prefix),
                    "stack_marker": {"name": "parent_pid", "value": str(parent_pid)},
                    "ownership_evidence": {
                        "parent_pid_match": True,
                        "start_after_parent": True,
                        "exe_path_fragment": exe_fragment,
                        "cmdline_fingerprint": command_line_fingerprint(cmdline or exe),
                    },
                },
            )
            registered.append(entry)
            seen_pids.add(pid)
        if registered:
            break
        time.sleep(interval_s)
    return registered


def main() -> int:
    parser = argparse.ArgumentParser()
    sub = parser.add_subparsers(dest="cmd", required=True)

    launch = sub.add_parser("launch", help="launch a process and register it at creation")
    launch.add_argument("--manifest", required=True, type=Path)
    launch.add_argument("--role", required=True)
    launch.add_argument("--command-line", required=True)
    launch.add_argument("--file-path", required=True)
    launch.add_argument("--arguments", default="")
    launch.add_argument("--working-directory", default=".")
    launch.add_argument("--pid-file", type=Path, default=None)
    launch.add_argument("--instance-marker", default=None)

    attach = sub.add_parser("attach-children", help="register children of an owned launcher PID")
    attach.add_argument("--manifest", required=True, type=Path)
    attach.add_argument("--parent-pid", required=True, type=int)
    attach.add_argument("--role-prefix", required=True)
    attach.add_argument("--exe-fragment", required=True)
    attach.add_argument("--max-wait", type=float, default=20.0)

    argv = sys.argv[1:]
    # argparse rejects option-like values (e.g. --arguments "-cmd=x"); convert to
    # the equals form so the raw argument string is preserved as a single value.
    for index, token in enumerate(argv):
        if token == "--arguments" and index + 1 < len(argv):
            argv = argv[:index] + [f"--arguments={argv[index + 1]}"] + argv[index + 2 :]
            break
    args = parser.parse_args(argv)

    if args.cmd == "attach-children":
        manifest = load_manifest(args.manifest)
        registered = attach_children(
            manifest,
            parent_pid=args.parent_pid,
            role_prefix=args.role_prefix,
            exe_fragment=args.exe_fragment,
            max_wait_s=args.max_wait,
        )
        save_manifest(manifest, args.manifest)
        for entry in registered:
            print(f"[attach] registered child pid={entry['pid']} role={entry['role']}")
        return 0

    file_name = Path(args.file_path).name.lower()
    creation_flags = subprocess.CREATE_NEW_CONSOLE if file_name == "cmd.exe" else 0
    launch_args = [args.file_path] + shlex.split(args.arguments, posix=False)
    try:
        proc = subprocess.Popen(
            launch_args,
            cwd=args.working_directory or None,
            creationflags=creation_flags,
        )
    except OSError as exc:
        # stdout so for /f callers in batch can surface the failure.
        print(f"[ERROR] failed to launch {args.file_path}: {exc}")
        return 1

    manifest = load_manifest(args.manifest)
    entry = register_process(
        manifest,
        side="windows",
        pid=proc.pid,
        role=args.role,
        name=Path(args.file_path).stem,
        # Register the EXACT command line handed to CreateProcess so identity
        # verification (PID + start-time + command-line fingerprint) matches
        # the process table.
        command_line=subprocess.list2cmdline(launch_args),
        reason="created via register_launcher.py (subprocess.Popen at creation)",
    )
    if args.instance_marker:
        entry["instance_marker"] = args.instance_marker
    save_manifest(manifest, args.manifest)
    if args.pid_file:
        args.pid_file.write_text(str(proc.pid), encoding="ascii")
    print(proc.pid)
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except Exception as exc:  # noqa: BLE001
        print(f"[ERROR] {exc}")
        raise SystemExit(1)
