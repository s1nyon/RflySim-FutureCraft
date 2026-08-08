"""Dual-UAV stack topology invariant (read-only): manifest + process tables.

The health gate must NOT pass merely because status files say ready. It must
also prove that the CURRENT stack owns exactly one valid instance of each
required component:

  windows:CopterSim/uav1  == exactly one alive, identity-matching owned entry
  windows:CopterSim/uav2  == exactly one alive, identity-matching owned entry
  wsl:px4_uav1            == at least the primary px4 -i 1 alive and matching;
                             every owned entry for uav1 alive and matching
  wsl:px4_uav2            == same for -i 2

All checks are ownership-based (manifest entries + PID/start-time/cmdline
identity verification). Name/regex is only used for role classification of
manifest entries, never to claim ownership. PID reuse (identity mismatch) or a
missing/duplicate instance makes the topology NOT READY.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Dict, List, Optional

from .process_table import find_by_pid
from .stack_manifest import entry_matches_process

COPTERSIM_ROLE_PREFIX = "gui:CopterSim/uav"
PX4_ROLE_PREFIX = "wsl:px4_uav"


@dataclass
class TopologyCheck:
    name: str
    ready: bool
    detail: str


@dataclass
class TopologyReport:
    ready: bool = False
    checks: List[TopologyCheck] = field(default_factory=list)
    reasons: List[str] = field(default_factory=list)
    evidence: Dict = field(default_factory=dict)


def _copter_entries(manifest: dict, instance: int) -> List[dict]:
    role = f"{COPTERSIM_ROLE_PREFIX}{instance}"
    return [e for e in manifest.get("windows_processes", []) if e.get("role") == role]


def _px4_entries(manifest: dict, instance: int) -> List[dict]:
    prefix = f"{PX4_ROLE_PREFIX}{instance}"
    return [e for e in manifest.get("wsl_processes", []) if str(e.get("role", "")).startswith(prefix)]


def _instance_ok(
    entries: List[dict],
    processes,
    instance: int,
    label: str,
    report: TopologyReport,
    require_exactly_one: bool,
) -> bool:
    if not entries:
        report.reasons.append(f"{label} uav{instance}: no owned entry in manifest")
        report.checks.append(TopologyCheck(f"{label}_uav{instance}", False, "no owned entry"))
        return False

    alive_match: List[dict] = []
    dead: List[dict] = []
    stale: List[dict] = []
    for entry in entries:
        proc = find_by_pid(processes, entry["pid"])
        if proc is None:
            dead.append(entry)
        elif entry_matches_process(entry, proc):
            alive_match.append(entry)
        else:
            stale.append(entry)

    if require_exactly_one and len(alive_match) != 1:
        report.reasons.append(
            f"{label} uav{instance}: expected exactly one alive owned instance, "
            f"found alive={len(alive_match)} dead={len(dead)} stale={len(stale)}"
        )
        report.checks.append(
            TopologyCheck(
                f"{label}_uav{instance}",
                False,
                f"alive={len(alive_match)} dead={len(dead)} stale={len(stale)}",
            )
        )
        return False
    if not require_exactly_one and not alive_match:
        report.reasons.append(
            f"{label} uav{instance}: no alive owned primary entry "
            f"(dead={len(dead)} stale={len(stale)})"
        )
        report.checks.append(
            TopologyCheck(f"{label}_uav{instance}", False, "primary not alive")
        )
        return False
    if dead or stale:
        report.reasons.append(
            f"{label} uav{instance}: {len(dead)} dead and {len(stale)} stale/identity-mismatch owned entry/ies"
        )
        report.checks.append(
            TopologyCheck(
                f"{label}_uav{instance}",
                False,
                f"dead={len(dead)} stale={len(stale)}",
            )
        )
        return False

    alive_pids = {int(e["pid"]) for e in alive_match}
    if len(alive_pids) != len(alive_match):
        report.reasons.append(f"{label} uav{instance}: duplicate PID across owned entries")
        report.checks.append(TopologyCheck(f"{label}_uav{instance}", False, "duplicate PID"))
        return False

    detail = ";".join(
        f"pid={e['pid']} start={e.get('start_time_utc', '')} role={e.get('role', '')}"
        for e in alive_match
    )
    report.checks.append(TopologyCheck(f"{label}_uav{instance}", True, detail))
    report.evidence[f"{label}_uav{instance}"] = {
        "ready": True,
        "pids": [int(e["pid"]) for e in alive_match],
        "roles": [e.get("role") for e in alive_match],
        "start_times": [e.get("start_time_utc", "") for e in alive_match],
    }
    return True


def _px4_ok(manifest: dict, processes, instance: int, report: TopologyReport) -> bool:
    """PX4 instance check: exactly one alive primary (role wsl:px4_uavN) AND every
    owned entry for the instance (including subsidiary px4-* roles) alive+matching."""
    all_entries = _px4_entries(manifest, instance)
    primary = [e for e in all_entries if e.get("role") == f"{PX4_ROLE_PREFIX}{instance}"]
    ok = _instance_ok(primary, processes, instance, "PX4", report, require_exactly_one=True)

    dead = [e for e in all_entries if find_by_pid(processes, e["pid"]) is None]
    stale = []
    for e in all_entries:
        proc = find_by_pid(processes, e["pid"])
        if proc is not None and not entry_matches_process(e, proc):
            stale.append(e)
    if dead or stale:
        report.reasons.append(
            f"PX4 uav{instance}: {len(dead)} dead and {len(stale)} stale owned entry/ies "
            "(including subsidiary px4-* roles)"
        )
        report.checks.append(
            TopologyCheck(
                f"PX4_uav{instance}",
                False,
                f"subsidiary dead={len(dead)} stale={len(stale)}",
            )
        )
        ok = False
    return ok


def check_topology(manifest: dict, win_table, wsl_table) -> TopologyReport:
    """Return True only when the dual-UAV instance topology is complete and owned."""
    report = TopologyReport()
    win_procs = win_table.snapshot()
    wsl_procs = wsl_table.snapshot()

    ok = True
    for instance in (1, 2):
        ok = _instance_ok(
            _copter_entries(manifest, instance),
            win_procs,
            instance,
            "CopterSim",
            report,
            require_exactly_one=True,
        ) and ok
    for instance in (1, 2):
        ok = _px4_ok(manifest, wsl_procs, instance, report) and ok

    # Cross-instance PID uniqueness (two instances must never share a PID).
    copter_pids = []
    for instance in (1, 2):
        for e in _copter_entries(manifest, instance):
            copter_pids.append((f"gui:CopterSim/uav{instance}", int(e["pid"])))
    px4_pids = []
    for instance in (1, 2):
        for e in _px4_entries(manifest, instance):
            px4_pids.append((f"wsl:px4_uav{instance}", int(e["pid"])))
    seen: Dict[int, str] = {}
    for role, pid in copter_pids + px4_pids:
        if pid in seen:
            report.reasons.append(f"duplicate PID {pid} claimed by both {seen[pid]} and {role}")
            report.checks.append(TopologyCheck("pid_uniqueness", False, f"PID {pid} duplicated across instances"))
            ok = False
        seen[pid] = role
    if ok and "pid_uniqueness" not in [c.name for c in report.checks]:
        report.checks.append(TopologyCheck("pid_uniqueness", True, "all instance PIDs distinct"))

    report.ready = ok
    report.evidence["stack_id"] = manifest.get("stack_id")
    report.evidence["ready"] = ok
    return report


def report_to_dict(report: TopologyReport) -> dict:
    return {
        "ready": report.ready,
        "checks": [{"name": c.name, "ready": c.ready, "detail": c.detail} for c in report.checks],
        "reasons": report.reasons,
        "evidence": report.evidence,
    }


def _cli_main() -> int:
    import argparse
    import json
    import sys
    from pathlib import Path

    from .process_table import WindowsProcessTable, WslProcessTable
    from .stack_manifest import load_manifest

    parser = argparse.ArgumentParser()
    parser.add_argument("--manifest", required=True, type=Path)
    parser.add_argument("--distro", default="RflySim-20.04")
    args = parser.parse_args()

    manifest = load_manifest(args.manifest)
    report = check_topology(manifest, WindowsProcessTable(), WslProcessTable(args.distro))
    print(json.dumps(report_to_dict(report), indent=2, ensure_ascii=False))
    return 0 if report.ready else 1


if __name__ == "__main__" and __package__ is None:
    sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
    from lifecycle import stack_topology as _self

    raise SystemExit(_self._cli_main())
