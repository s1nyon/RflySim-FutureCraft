#!/usr/bin/env python3
"""Write the Stage 7 flight report even when live execution fails."""

from __future__ import annotations

import argparse
import json
from pathlib import Path


REQUIRED_EVENTS = (
    "offboard_confirmed",
    "arming_confirmed",
    "takeoff_altitude_confirmed",
    "landing_confirmed",
    "navigation_confirmed",
)
UAV_IDS = ("uav1", "uav2")


def _read_json(path):
    return json.loads(path.read_text(encoding="utf-8")) if path.exists() else None


def _read_events(path):
    if not path.exists():
        return []
    return [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines() if line.strip()]


def _last_error(path):
    if not path.exists():
        return "executor log was not written"
    lines = [line.strip() for line in path.read_text(encoding="utf-8", errors="replace").splitlines() if line.strip()]
    return lines[-1] if lines else "executor exited without an error message"


def build_report(
    smoke_path,
    events_path,
    trace_path,
    score_path,
    executor_log_path,
    executor_exit_code,
    run_id=None,
    phase="executor",
):
    events = _read_events(events_path)
    checks = {name: {uav_id: False for uav_id in UAV_IDS} for name in REQUIRED_EVENTS}
    for event in events:
        name = event.get("event")
        uav_id = event.get("uav")
        if name in checks and uav_id in checks[name]:
            checks[name][uav_id] = True

    executor = {"exit_code": executor_exit_code, "log": str(executor_log_path)}
    if executor_exit_code != 0:
        executor["error"] = _last_error(executor_log_path)

    smoke = _read_json(smoke_path)
    trace = _read_json(trace_path)
    score = _read_json(score_path)
    artifacts_valid = trace is not None and score is not None
    smoke_ready = isinstance(smoke, dict) and smoke.get("ready") is True
    report = {
        "stage": "stage7_live_slam_ego_swarm_flight",
        "phase": phase,
        "ready": (
            executor_exit_code == 0
            and smoke_ready
            and artifacts_valid
            and all(all(values.values()) for values in checks.values())
        ),
        "executor": executor,
        "smoke_report": str(smoke_path),
        "mission_events": str(events_path),
        "executor_trace": str(trace_path),
        "score_summary": str(score_path),
        "checks": checks,
    }
    if run_id is not None:
        report["run_id"] = run_id
    if smoke is not None:
        report["smoke"] = smoke
    if score is not None:
        report["score"] = score
    return report


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--smoke-report", required=True, type=Path)
    parser.add_argument("--events", required=True, type=Path)
    parser.add_argument("--trace", required=True, type=Path)
    parser.add_argument("--score", required=True, type=Path)
    parser.add_argument("--executor-log", required=True, type=Path)
    parser.add_argument("--executor-exit-code", required=True, type=int)
    parser.add_argument("--run-id", required=True)
    parser.add_argument("--phase", default="executor")
    parser.add_argument("--report", required=True, type=Path)
    args = parser.parse_args(argv)
    report = build_report(
        args.smoke_report,
        args.events,
        args.trace,
        args.score,
        args.executor_log,
        args.executor_exit_code,
        run_id=args.run_id,
        phase=args.phase,
    )
    args.report.parent.mkdir(parents=True, exist_ok=True)
    args.report.write_text(json.dumps(report, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    return 0 if report["ready"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
