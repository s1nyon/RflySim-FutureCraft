#!/usr/bin/env python3
"""Behavior checks for Stage 7 plan generation and failure reporting."""

from __future__ import annotations

import argparse
import importlib.util
import json
import tempfile
from pathlib import Path


def load_module(name: str, module_path: Path):
    spec = importlib.util.spec_from_file_location(name, str(module_path))
    if spec is None or spec.loader is None:
        raise RuntimeError(f"cannot load module: {module_path}")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--plan-module", required=True, type=Path)
    parser.add_argument("--report-module", required=True, type=Path)
    parser.add_argument("--artifacts-module", required=True, type=Path)
    parser.add_argument("--config", required=True, type=Path)
    args = parser.parse_args()

    plan_module = load_module("stage7_flight_plan", args.plan_module)
    report_module = load_module("stage7_flight_report", args.report_module)
    artifacts_module = load_module("stage7_run_artifacts", args.artifacts_module)
    config = json.loads(args.config.read_text(encoding="utf-8"))

    plan = plan_module.build_plan(config)
    planner_actions = [
        action for action in plan["actions"] if action["action"] == "publish_planner_goal"
    ]
    assert [action["topic"] for action in planner_actions] == [
        "/uav1/planning/goal",
        "/uav2/planning/goal",
    ], "planner goals must remain isolated by UAV namespace"

    with tempfile.TemporaryDirectory() as temp_dir:
        output_dir = Path(temp_dir)
        for name in (
            "flight_report.json",
            "mission_events.jsonl",
            "executor_trace.json",
            "score_summary.json",
            "executor.log",
            "slam_ego_swarm_smoke_report.json",
            "live_slam_ego_swarm_plan.json",
        ):
            (output_dir / name).write_text("stale-ready-evidence\n", encoding="utf-8")

        artifacts_module.begin_run(output_dir, "run-123")
        initial_report = json.loads((output_dir / "flight_report.json").read_text(encoding="utf-8"))
        assert initial_report["ready"] is False
        assert initial_report["run_id"] == "run-123"
        assert initial_report["phase"] == "starting"
        for name in (
            "mission_events.jsonl",
            "executor_trace.json",
            "score_summary.json",
            "executor.log",
            "slam_ego_swarm_smoke_report.json",
            "live_slam_ego_swarm_plan.json",
        ):
            assert not (output_dir / name).exists(), f"stale artifact was not cleared: {name}"

        smoke_path = output_dir / "smoke.json"
        executor_log_path = output_dir / "executor.log"
        report_path = output_dir / "flight_report.json"
        smoke_path.write_text('{"ready": true}\n', encoding="utf-8")
        executor_log_path.write_text("arming failed\n", encoding="utf-8")

        exit_code = report_module.main(
            [
                "--smoke-report",
                str(smoke_path),
                "--events",
                str(output_dir / "missing-events.jsonl"),
                "--trace",
                str(output_dir / "missing-trace.json"),
                "--score",
                str(output_dir / "missing-score.json"),
                "--executor-log",
                str(executor_log_path),
                "--executor-exit-code",
                "7",
                "--run-id",
                "run-123",
                "--phase",
                "executor",
                "--report",
                str(report_path),
            ]
        )

        report = json.loads(report_path.read_text(encoding="utf-8"))
        assert exit_code == 1
        assert report["ready"] is False
        assert report["executor"]["exit_code"] == 7
        assert report["executor"]["log"] == str(executor_log_path)
        assert report["executor"]["error"] == "arming failed"

        complete_events = []
        for event_name in (
            "offboard_confirmed",
            "arming_confirmed",
            "takeoff_altitude_confirmed",
            "landing_confirmed",
        ):
            for uav_id in ("uav1", "uav2"):
                complete_events.append({"event": event_name, "uav": uav_id})
        events_path = output_dir / "complete-events.jsonl"
        events_path.write_text(
            "".join(json.dumps(event) + "\n" for event in complete_events),
            encoding="utf-8",
        )
        trace_path = output_dir / "trace.json"
        score_path = output_dir / "score.json"
        trace_path.write_text("[]\n", encoding="utf-8")
        score_path.write_text('{"status": "complete"}\n', encoding="utf-8")
        without_navigation = report_module.build_report(
            smoke_path,
            events_path,
            trace_path,
            score_path,
            executor_log_path,
            0,
            run_id="run-123",
            phase="executor",
        )
        assert without_navigation["ready"] is False
        assert without_navigation["run_id"] == "run-123"
        assert without_navigation["phase"] == "executor"

        for uav_id in ("uav1", "uav2"):
            complete_events.append({"event": "navigation_confirmed", "uav": uav_id})
        events_path.write_text(
            "".join(json.dumps(event) + "\n" for event in complete_events),
            encoding="utf-8",
        )
        with_navigation = report_module.build_report(
            smoke_path,
            events_path,
            trace_path,
            score_path,
            executor_log_path,
            0,
            run_id="run-123",
            phase="complete",
        )
        assert with_navigation["ready"] is True

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
