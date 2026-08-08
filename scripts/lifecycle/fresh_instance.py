"""Fresh-instance sequence: fixed phases, gates, no auto force-retry."""

from __future__ import annotations

from typing import Optional

FRESH_INSTANCE_PHASES = [
    "inspect",
    "graceful_stop",
    "verify_clean",
    "start_new",
    "health_gate",
    "readiness",
    "flight",
]

PHASE_GATES = {
    "inspect": "read-only; report unknown/stale; fail closed before any stop",
    "graceful_stop": "manifest-only graceful stop; DryRun first; no global process-kill / no WSL distribution shutdown / no name scan",
    "verify_clean": "no owned alive, no unknown, no stale; otherwise abort and report (NO auto force retry)",
    "start_new": "new stack_id and new simulation_instance_id; never reuse previous readiness",
    "health_gate": "GUI_READY / ROSCORE_READY / MAVROS_UAV1_CONNECTED / MAVROS_UAV2_CONNECTED / COURSE_READY all ready",
    "readiness": "Stage 7 no-arm readiness for the new instance",
    "flight": "only after readiness; --simulation-only --allow-arm policy gates apply",
}


def build_plan(existing_manifest: Optional[dict] = None) -> dict:
    return {
        "schema_version": 1,
        "stack_id": existing_manifest.get("stack_id") if existing_manifest else None,
        "auto_force_retry": False,
        "records": ["startup_success", "flight_success", "shutdown_clean"],
        "phases": [
            {"name": name, "gate": PHASE_GATES[name]} for name in FRESH_INSTANCE_PHASES
        ],
    }


def _report_counts(report) -> dict:
    if hasattr(report, "owned"):
        owned_alive = sum(1 for item in report.owned if item.status == "owned_and_alive")
        owned_exited = sum(1 for item in report.owned if item.status == "owned_but_exited")
        stale = len(report.stale)
        unknown = len(report.unknown_suspicious)
        ports_unknown = sum(1 for p in report.ports if p.occupied and p.owned is False)
    else:
        owned_alive = int(getattr(report, "owned_alive", 0))
        owned_exited = int(getattr(report, "owned_exited", 0))
        stale = int(getattr(report, "stale", 0))
        unknown = int(getattr(report, "unknown", 0))
        ports_unknown = int(getattr(report, "ports_unknown", 0))
    return {
        "owned_alive": owned_alive,
        "owned_exited": owned_exited,
        "orphans": int(getattr(report, "orphans", 0)),
        "stale": stale,
        "unknown": unknown,
        "ports_unknown": ports_unknown,
    }


def verify_clean_decision(report) -> tuple:
    counts = _report_counts(report)
    reasons: list = []
    if counts["owned_alive"]:
        reasons.append(f"{counts['owned_alive']} owned process(es) still alive")
    if counts["orphans"]:
        reasons.append(f"{counts['orphans']} owned orphan process group(s) still alive")
    if counts["stale"]:
        reasons.append(f"{counts['stale']} stale/PID-reuse record(s)")
    if counts["unknown"]:
        reasons.append(f"{counts['unknown']} unknown suspicious process(es)")
    if counts["ports_unknown"]:
        reasons.append(f"{counts['ports_unknown']} required port(s) occupied by unknown process")
    return (len(reasons) == 0, reasons)


def can_proceed_to_start(report) -> bool:
    if hasattr(report, "fail_closed"):
        counts = _report_counts(report)
        return not bool(report.fail_closed) and counts["orphans"] == 0
    return not _report_counts(report)["stale"] and not _report_counts(report)["unknown"] and not _report_counts(report)["ports_unknown"]
