"""Explicit metadata-only retirement for a manifest whose stack is proven dead.

This module deliberately has no stop backend and sends no process signal.  It
only archives ownership records after two identical fail-closed snapshots.
"""

from __future__ import annotations

import copy
import hashlib
import json
import subprocess
import sys
from dataclasses import dataclass, field
from pathlib import Path
from typing import List, Optional

if __name__ == "__main__" and __package__ is None:
    sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
    from lifecycle import stack_retire_stale as _self

    raise SystemExit(_self._cli_main())

from .process_table import WindowsProcessTable, WslProcessTable, find_by_pgid, find_by_pid
from .stack_inspect import (
    WINDOWS_STACK_NAMES,
    WSL_SUSPICIOUS_PATTERNS,
    WslAwarePortsProbe,
    inspect_stack,
    summarize,
)
from .stack_manifest import (
    command_line_fingerprint,
    entry_matches_process,
    load_manifest,
    save_manifest,
    utc_now_iso,
)


class RetirementError(RuntimeError):
    pass


@dataclass
class RetirementPlan:
    stack_id: str
    eligible: bool
    denial_reasons: List[str]
    entries: List[dict]
    summary: dict
    ports: List[dict]
    ros: dict
    plan_token: str = ""
    planned_process_signals: List[str] = field(default_factory=list)


def _identity_from_entry(entry: dict) -> dict:
    return {
        "pid": int(entry["pid"]),
        "name": str(entry.get("name", "")),
        "start_time_utc": str(entry.get("start_time_utc", "")),
        "command_line": str(entry.get("command_line", "")),
        "command_fingerprint": command_line_fingerprint(entry.get("command_line", "")),
        "pgid": entry.get("pgid"),
    }


def _identity_from_process(proc) -> Optional[dict]:
    if proc is None:
        return None
    return {
        "pid": int(proc.pid),
        "name": str(getattr(proc, "name", "")),
        "start_time_utc": str(getattr(proc, "start_time_utc", "")),
        "command_line": str(getattr(proc, "command_line", "")),
        "command_fingerprint": command_line_fingerprint(getattr(proc, "command_line", "")),
        "parent_pid": int(getattr(proc, "parent_pid", 0)),
        "pgid": getattr(proc, "pgid", None),
    }


def _token_payload(plan: RetirementPlan) -> dict:
    return {
        "stack_id": plan.stack_id,
        "eligible": plan.eligible,
        "denial_reasons": plan.denial_reasons,
        "entries": plan.entries,
        "summary": plan.summary,
        "ports": plan.ports,
        "ros": plan.ros,
        "planned_process_signals": plan.planned_process_signals,
    }


def _set_plan_token(plan: RetirementPlan) -> RetirementPlan:
    payload = json.dumps(_token_payload(plan), sort_keys=True, separators=(",", ":"))
    plan.plan_token = hashlib.sha256(payload.encode("utf-8")).hexdigest()
    return plan


def plan_to_dict(plan: RetirementPlan) -> dict:
    return {
        **_token_payload(plan),
        "plan_token": plan.plan_token,
        "planned_metadata_changes": {
            "remove_from_active_ownership": [
                {"side": item["side"], "role": item["role"], "recorded_pid": item["recorded_pid"]}
                for item in plan.entries
            ],
            "append_to": "stop.retired_stale_ownership",
        },
    }


def _capture_processes(win_table, wsl_table):
    win_snapshot = win_table.snapshot()
    win_error = getattr(win_table, "last_error", None)
    wsl_snapshot = wsl_table.snapshot()
    wsl_error = getattr(wsl_table, "last_error", None)
    return win_snapshot, wsl_snapshot, win_error, wsl_error


def build_retirement_plan(manifest, win_table, wsl_table, ports_probe, ros_probe) -> RetirementPlan:
    win_snapshot, wsl_snapshot, win_error, wsl_error = _capture_processes(win_table, wsl_table)

    class SnapshotTable:
        def __init__(self, values):
            self.values = list(values)

        def snapshot(self):
            return list(self.values)

    report = inspect_stack(
        manifest,
        win_table=SnapshotTable(win_snapshot),
        wsl_table=SnapshotTable(wsl_snapshot),
        ports_probe=ports_probe,
        ros_probe=ros_probe,
    )
    summary = summarize(report)
    denial: List[str] = []
    if summary["owned_and_alive"]:
        denial.append(f"owned_and_alive={summary['owned_and_alive']}")
    if summary["owned_orphan"]:
        denial.append(f"owned_orphan={summary['owned_orphan']}")
    if summary["unknown_suspicious"]:
        denial.append(f"unknown_suspicious={summary['unknown_suspicious']}")
    occupied_ports = [item for item in report.ports if item.occupied]
    if occupied_ports:
        denial.append(f"required_ports_not_clean={len(occupied_ports)}")
    ambiguous_ports = [
        item for item in report.ports
        if not item.occupied and not str(item.detail).lower().startswith("free")
    ]
    if ambiguous_ports:
        denial.append(f"port_probe_ambiguous={len(ambiguous_ports)}")
    if win_error:
        denial.append(f"windows_process_probe_ambiguous={win_error}")
    if wsl_error:
        denial.append(f"wsl_process_probe_ambiguous={wsl_error}")
    probe_errors = list(getattr(ros_probe, "probe_errors", []))
    if probe_errors:
        denial.append("ros_probe_ambiguous=" + ";".join(probe_errors))
    ros = {
        "roscore_alive": bool(report.ros.roscore_alive),
        "mavros_uav1_connected": bool(report.ros.mavros_uav1_connected),
        "mavros_uav2_connected": bool(report.ros.mavros_uav2_connected),
        "course_ready": bool(report.ros.course_ready),
    }
    if any(ros.values()):
        denial.append("ros_or_stack_activity_detected")

    entries: List[dict] = []
    suspicious_stale_occupants = 0
    for side, key, snapshot in (
        ("windows", "windows_processes", win_snapshot),
        ("wsl", "wsl_processes", wsl_snapshot),
    ):
        for entry in manifest[key]:
            current = find_by_pid(snapshot, entry["pid"])
            group = find_by_pgid(snapshot, entry.get("pgid")) if side == "wsl" and entry.get("pgid") else []
            if current is not None and entry_matches_process(entry, current):
                continue
            if group:
                continue
            if current is not None:
                current_name = str(getattr(current, "name", ""))
                normalized_name = current_name[:-4] if current_name.lower().endswith(".exe") else current_name
                current_command = str(getattr(current, "command_line", ""))
                if (
                    side == "windows" and normalized_name in WINDOWS_STACK_NAMES
                ) or (
                    side == "wsl" and any(pattern.search(current_command) for pattern in WSL_SUSPICIOUS_PATTERNS)
                ):
                    suspicious_stale_occupants += 1
            reason = "recorded_pid_absent" if current is None else "pid_identity_mismatch"
            entries.append({
                "side": side,
                "role": str(entry["role"]),
                "recorded_pid": int(entry["pid"]),
                "recorded_identity": _identity_from_entry(entry),
                "observed_pid": int(current.pid) if current is not None else None,
                "observed_identity": _identity_from_process(current),
                "retirement_reason": reason,
                "signal_sent": False,
            })
    if suspicious_stale_occupants:
        denial.append(f"stale_pid_occupied_by_suspicious_process={suspicious_stale_occupants}")
    if not entries:
        denial.append("no_dead_or_stale_ownership_entries")

    ports = [
        {
            "port": int(item.port),
            "protocol": str(item.protocol),
            "occupied": bool(item.occupied),
            "owned": item.owned,
            "detail": str(item.detail),
        }
        for item in report.ports
    ]
    plan = RetirementPlan(
        stack_id=str(manifest.get("stack_id", "")),
        eligible=not denial,
        denial_reasons=denial,
        entries=entries,
        summary=summary,
        ports=ports,
        ros=ros,
        planned_process_signals=[],
    )
    return _set_plan_token(plan)


def execute_retirement(
    manifest,
    win_table,
    wsl_table,
    ports_probe,
    ros_probe,
    *,
    expected_plan_token: str,
    before_commit=None,
) -> RetirementPlan:
    first = build_retirement_plan(manifest, win_table, wsl_table, ports_probe, ros_probe)
    if not first.eligible:
        raise RetirementError("retirement admission denied: " + ", ".join(first.denial_reasons))
    if not expected_plan_token or first.plan_token != expected_plan_token:
        raise RetirementError("DryRun plan token does not match current full snapshot")
    if before_commit is not None:
        before_commit()
    final = build_retirement_plan(manifest, win_table, wsl_table, ports_probe, ros_probe)
    if not final.eligible or final.plan_token != first.plan_token:
        raise RetirementError("state changed after admission; manifest unchanged")

    retired_at = utc_now_iso()
    audit = []
    retirement_keys = {
        (item["side"], int(item["recorded_pid"]), item["role"])
        for item in final.entries
    }
    for item in final.entries:
        record = copy.deepcopy(item)
        record["retired_at_utc"] = retired_at
        audit.append(record)
    manifest["windows_processes"] = [
        entry for entry in manifest["windows_processes"]
        if ("windows", int(entry["pid"]), str(entry["role"])) not in retirement_keys
    ]
    manifest["wsl_processes"] = [
        entry for entry in manifest["wsl_processes"]
        if ("wsl", int(entry["pid"]), str(entry["role"])) not in retirement_keys
    ]
    stop = manifest.setdefault("stop", {})
    previous_pids = [int(value) for value in stop.get("retired_stale_entries", []) if isinstance(value, int)]
    stop["retired_stale_entries"] = list(dict.fromkeys(
        previous_pids + [int(item["recorded_pid"]) for item in final.entries]
    ))
    stop.setdefault("retired_stale_ownership", []).extend(audit)
    stop["last_stale_retirement"] = {
        "retired_at_utc": retired_at,
        "plan_token": final.plan_token,
        "entry_count": len(audit),
        "signal_sent": False,
    }
    return final


class ProvenWslRosProbe:
    """Read-only ROS activity probe that distinguishes inactivity from probe failure."""

    def __init__(self, distro: str = "RflySim-20.04"):
        self.distro = distro
        self.probe_errors: List[str] = []

    def _active(self, label: str, command: str) -> bool:
        try:
            result = subprocess.run(
                ["wsl.exe", "-d", self.distro, "-e", "bash", "-lic", command],
                capture_output=True, text=True, encoding="utf-8", errors="replace", timeout=30,
            )
        except (subprocess.SubprocessError, OSError) as exc:
            self.probe_errors.append(f"{label}:{exc}")
            return False
        if result.returncode not in (0, 1, 124):
            self.probe_errors.append(f"{label}:exit={result.returncode}")
            return False
        return result.returncode == 0

    def roscore_alive(self) -> bool:
        return self._active("roscore", "timeout 5s rostopic list >/dev/null 2>&1")

    def mavros_connected(self, ns: str) -> bool:
        return self._active(
            f"mavros_{ns}",
            f"timeout 5s rostopic echo -n 1 /{ns}/mavros/state 2>/dev/null | grep -q 'connected: True'",
        )

    def course_ready(self) -> bool:
        return self._active(
            "course",
            "timeout 5s rostopic info /predicted_narrow_course/global_cloud 2>/dev/null | "
            "grep -q 'Publishers:' && ! timeout 5s rostopic info "
            "/predicted_narrow_course/global_cloud 2>/dev/null | grep -q 'Publishers: None'",
        )


def _cli_main() -> int:
    import argparse

    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--manifest", required=True, type=Path)
    parser.add_argument("--distro", default="RflySim-20.04")
    parser.add_argument("--execute", action="store_true")
    parser.add_argument("--plan-token")
    args = parser.parse_args()
    if args.execute and not args.plan_token:
        parser.error("--execute requires the exact --plan-token printed by DryRun")

    manifest = load_manifest(args.manifest)
    win_table = WindowsProcessTable()
    wsl_table = WslProcessTable(args.distro)
    ports_probe = WslAwarePortsProbe(
        [int(entry["pid"]) for entry in manifest["windows_processes"]],
        [int(entry["pid"]) for entry in manifest["wsl_processes"]],
        args.distro,
    )
    ros_probe = ProvenWslRosProbe(args.distro)
    try:
        if args.execute:
            plan = execute_retirement(
                manifest, win_table, wsl_table, ports_probe, ros_probe,
                expected_plan_token=args.plan_token,
            )
            save_manifest(manifest, args.manifest)
        else:
            plan = build_retirement_plan(manifest, win_table, wsl_table, ports_probe, ros_probe)
    except RetirementError as exc:
        print(f"[retire-stale] ABORT: {exc}", file=sys.stderr)
        return 2
    output = plan_to_dict(plan)
    output["manifest"] = str(args.manifest.resolve())
    output["mode"] = "execute" if args.execute else "dry-run"
    print(json.dumps(output, indent=2, ensure_ascii=False))
    print("[retire-stale] planned process signals: NONE", file=sys.stderr)
    if not plan.eligible:
        print("[retire-stale] FAIL-CLOSED: retirement admission denied", file=sys.stderr)
        return 2
    if args.execute:
        print("[retire-stale] metadata retirement committed; no process signal sent", file=sys.stderr)
    else:
        print("[retire-stale] eligible DryRun; Execute requires this exact plan token", file=sys.stderr)
    return 0


if __name__ == "__main__":
    raise SystemExit(_cli_main())
