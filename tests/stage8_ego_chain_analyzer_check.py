#!/usr/bin/env python3
"""Offline regression guard for the EGO execution-chain analyzer.

Verifies that ``stage8_ego_chain_analyzer.py`` turns recorder JSONL events into
per-goal segments and flags the first broken stage.  The fixture models a
healthy UAV and a UAV whose second navigation goal produces bspline but no
``planner_command`` (the P0.5 intermittent signature).
"""

from __future__ import annotations

import argparse
import importlib.util
import sys
from pathlib import Path


def load_analyzer(module_path):
    spec = importlib.util.spec_from_file_location(
        "stage8_ego_chain_analyzer", str(module_path)
    )
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def make_event(kind, uav_id, monotonic, position=None):
    event = {
        "kind": kind,
        "uav_id": uav_id,
        "receive_wall_time": float(monotonic),
        "receive_monotonic": float(monotonic),
        "header_stamp": float(monotonic),
    }
    if position is not None:
        event["position"] = [float(value) for value in position]
    return event


def build_fixture():
    events = []
    start = 100.0
    for goal_index in range(3):
        goal_time = start + goal_index * 10.0
        events.append(
            make_event("planner_goal", "uav1", goal_time, [goal_index * 2.0, 0.0, 1.0])
        )
        events.append(make_event("traj_start_trigger", "uav1", goal_time + 0.05))
        events.append(make_event("bspline", "uav1", goal_time + 0.10))
        for step in range(5):
            events.append(
                make_event("planner_command", "uav1", goal_time + 0.2 + step * 0.1)
            )
        events.append(
            make_event("setpoint_target", "uav1", goal_time + 0.25)
        )
        events.append(
            make_event("local_position", "uav1", goal_time + 0.30)
        )

    for goal_index in range(2):
        goal_time = start + 1.0 + goal_index * 10.0
        events.append(
            make_event("planner_goal", "uav2", goal_time, [goal_index * 2.0, 0.0, 1.0])
        )
        events.append(make_event("traj_start_trigger", "uav2", goal_time + 0.05))
        events.append(make_event("bspline", "uav2", goal_time + 0.10))
        if goal_index == 0:
            for step in range(5):
                events.append(
                    make_event("planner_command", "uav2", goal_time + 0.2 + step * 0.1)
                )
            events.append(
                make_event("setpoint_target", "uav2", goal_time + 0.25)
            )
            events.append(
                make_event("local_position", "uav2", goal_time + 0.30)
            )
    return events


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--analyzer-module", required=True, type=Path)
    args = parser.parse_args()

    analyzer = load_analyzer(args.analyzer_module)
    report = analyzer.build_report(build_fixture(), pre_roll_sec=1.0)

    assert report["event_count"] == 43, report["event_count"]
    uav1 = report["uavs"]["uav1"]
    uav2 = report["uavs"]["uav2"]
    assert uav1["goal_count"] == 3
    assert uav1["segments_with_bspline"] == 3
    assert uav1["segments_with_pos_cmd"] == 3
    assert uav2["goal_count"] == 2
    assert uav2["segments_with_bspline"] == 2
    assert uav2["segments_with_pos_cmd"] == 1

    uav2_segments = [s for s in report["segments"] if s["uav_id"] == "uav2"]
    assert uav2_segments[0]["chain_complete"] is True
    assert uav2_segments[0]["control_feedback_present"] is True
    assert uav2_segments[1]["chain_complete"] is False
    assert uav2_segments[1]["stages"]["bspline"]["count"] == 1
    assert uav2_segments[1]["stages"]["planner_command"]["count"] == 0
    assert uav2_segments[1]["stages"]["planner_command"]["first_monotonic"] is None
    assert uav2_segments[1]["executor_proceeded"] is False

    uav1_segments = [s for s in report["segments"] if s["uav_id"] == "uav1"]
    assert all(segment["chain_complete"] for segment in uav1_segments)
    assert uav1_segments[0]["executor_proceeded"] is True
    assert uav1_segments[-1]["executor_proceeded"] is False
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
