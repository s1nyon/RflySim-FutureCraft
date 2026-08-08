"""Ownership: registration-at-creation only. Scanning/name/regex claiming is forbidden."""

from __future__ import annotations

import re
from typing import Optional, Sequence

from .stack_manifest import utc_now_iso


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
    failure_reasons: Optional[Sequence[str]] = None,
) -> None:
    manifest["stop"] = {
        "last_stop_reason": reason,
        "last_stop_utc": utc_now_iso(),
        "clean": clean,
        "force_reasons": list(force_reasons or []),
        "failure_reasons": list(failure_reasons or []),
    }


def record_health(manifest: dict, health: dict) -> None:
    manifest["health"] = health


def register_process(
    manifest: dict,
    side: str,
    pid: int,
    role: str,
    command_line: str,
    start_time_utc: Optional[str] = None,
    name: Optional[str] = None,
    pgid: Optional[int] = None,
    reason: Optional[str] = None,
) -> dict:
    """Grant ownership at creation. The caller must have obtained pid/pgid when it created the process."""
    if side not in ("windows", "wsl"):
        raise ValueError(f"invalid side: {side}")
    if not isinstance(pid, int) or pid <= 0:
        raise ValueError(f"invalid pid: {pid}")
    if not reason:
        raise ValueError("ownership grant requires an explicit reason (how the launcher obtained the PID at creation)")
    if not command_line:
        raise ValueError("ownership grant requires the command line captured at creation")

    target = manifest[f"{side}_processes"]
    existing = {int(e["pid"]) for e in target}
    if int(pid) in existing:
        raise ValueError(f"duplicate registration for side={side} pid={pid}; fix the launcher")

    entry = {
        "pid": int(pid),
        "name": str(name or ""),
        "start_time_utc": start_time_utc or utc_now_iso(),
        "command_line": str(command_line),
        "role": str(role),
        "verified_at_utc": utc_now_iso(),
        "ownership": {
            "granted": "at_creation",
            "reason": str(reason),
            "granted_at_utc": utc_now_iso(),
        },
    }
    if pgid is not None:
        entry["pgid"] = int(pgid)
    target.append(entry)
    return entry
