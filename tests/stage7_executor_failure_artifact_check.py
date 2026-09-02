#!/usr/bin/env python3
"""Executor failure paths must still write partial events, trace, and score artifacts."""

from __future__ import annotations

import argparse
import contextlib
import importlib.util
import io
import json
import sys
import tempfile
from pathlib import Path


def load_module(name: str, module_path: Path):
    sys.path.insert(0, str(module_path.parent))
    spec = importlib.util.spec_from_file_location(name, str(module_path))
    if spec is None or spec.loader is None:
        raise RuntimeError(f"cannot load module: {module_path}")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def _plan_with_actions(actions):
    return {
        "mission_name": "executor_failure_artifact_check",
        "actions": actions,
        "geofence": {
            "min_x": -1.0,
            "max_x": 17.0,
            "min_y": -2.0,
            "max_y": 7.0,
            "min_z": 0.0,
            "max_z": 2.0,
            "max_speed_mps": 2.0,
            "max_odom_age_s": 0.5,
        },
    }


def _goal_action(sequence, goal):
    return {
        "sequence": sequence,
        "stage": "collaborative_navigate",
        "action": "publish_planner_goal",
        "uav": "uav1",
        "topic": "/uav1/planning/goal",
        "goal": goal,
        "timeout_s": 5,
    }


def _run_executor(executor, plan, live_config, temp_dir):
    events_path = Path(temp_dir) / "mission_events.jsonl"
    trace_path = Path(temp_dir) / "executor_trace.json"
    score_path = Path(temp_dir) / "score_summary.json"
    plan_path = Path(temp_dir) / "plan.json"
    plan_path.write_text(json.dumps(plan, sort_keys=True), encoding="utf-8")
    with contextlib.redirect_stderr(io.StringIO()):
        exit_code = executor.main(
            [
                "--plan",
                str(plan_path),
                "--live-config",
                str(live_config),
                "--backend",
                "dry-run",
                "--events",
                str(events_path),
                "--trace",
                str(trace_path),
                "--score",
                str(score_path),
            ]
        )
    return exit_code, events_path, trace_path, score_path


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--executor-module", required=True, type=Path)
    parser.add_argument("--live-config", required=True, type=Path)
    args = parser.parse_args()

    executor = load_module("mission_executor", args.executor_module)

    with tempfile.TemporaryDirectory() as temp_dir:
        # Scenario 1: plan validation fails before any action runs.
        invalid_plan = _plan_with_actions(
            [
                {
                    "sequence": 1,
                    "stage": "collaborative_navigate",
                    "action": "explode",
                }
            ]
        )
        exit_code, events_path, trace_path, score_path = _run_executor(
            executor, invalid_plan, args.live_config, temp_dir
        )
        assert exit_code == 1, "invalid plan must still exit non-zero"
        events = [
            json.loads(line)
            for line in events_path.read_text(encoding="utf-8").splitlines()
            if line.strip()
        ]
        assert events[-1]["event"] == "mission_failed", events[-1]
        assert "error" in events[-1], "mission_failed event must record the error"
        trace = json.loads(trace_path.read_text(encoding="utf-8"))
        assert isinstance(trace, list), "trace must be a list on failure"
        score = json.loads(score_path.read_text(encoding="utf-8"))
        assert score["success"] is False, "failure score must report success=false"
        assert "missing_mission_end" in score["failure_reasons"]

    with tempfile.TemporaryDirectory() as temp_dir:
        # Scenario 2: an action fails after earlier actions succeeded, so the
        # partial trace must preserve the completed actions and the failing goal.
        partial_plan = _plan_with_actions(
            [
                _goal_action(1, {"x": 0.5, "y": 1.5, "z": 1.0}),
                _goal_action(2, {"x": 100.0, "y": 1.5, "z": 1.0}),
            ]
        )
        exit_code, events_path, trace_path, score_path = _run_executor(
            executor, partial_plan, args.live_config, temp_dir
        )
        assert exit_code == 1
        events = [
            json.loads(line)
            for line in events_path.read_text(encoding="utf-8").splitlines()
            if line.strip()
        ]
        assert events[0]["event"] == "mission_start"
        assert events[-1]["event"] == "mission_failed"
        assert events[-1]["sequence"] == 2, "mission_failed must identify the failing action"
        trace = json.loads(trace_path.read_text(encoding="utf-8"))
        completed = [entry["sequence"] for entry in trace if entry.get("action") != "failed"]
        assert completed == [1], "partial trace must keep completed actions before the failure"
        assert trace[-1]["sequence"] == 2
        assert trace[-1]["action"] == "failed"
        assert "point is outside geofence" in trace[-1]["detail"]
        score = json.loads(score_path.read_text(encoding="utf-8"))
        assert score["success"] is False

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
