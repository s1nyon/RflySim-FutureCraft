#!/usr/bin/env python3
"""Behavior checks for the Stage 7 planner-command control bridge."""

from __future__ import annotations

import argparse
import importlib.util
import json
import sys
from pathlib import Path
from types import SimpleNamespace


def load_module(name, path):
    spec = importlib.util.spec_from_file_location(name, str(path))
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


class DummyPositionTarget:
    FRAME_LOCAL_NED = 1
    IGNORE_VX = 8
    IGNORE_VY = 16
    IGNORE_VZ = 32
    IGNORE_AFX = 64
    IGNORE_AFY = 128
    IGNORE_AFZ = 256
    FORCE = 512
    IGNORE_YAW_RATE = 2048

    def __init__(self):
        self.coordinate_frame = 0
        self.type_mask = 0
        self.position = SimpleNamespace(x=0.0, y=0.0, z=0.0)
        self.yaw = 0.0


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--bridge-module", required=True, type=Path)
    parser.add_argument("--plan-module", required=True, type=Path)
    parser.add_argument("--config", required=True, type=Path)
    parser.add_argument("--executor-module", required=True, type=Path)
    args = parser.parse_args()

    bridge = load_module("ego_swarm_setpoint_bridge", args.bridge_module)
    command = SimpleNamespace(
        position=SimpleNamespace(x=1.25, y=-0.5, z=1.1),
        yaw=0.75,
    )
    target = bridge.position_command_to_target(command, DummyPositionTarget)
    assert target.coordinate_frame == DummyPositionTarget.FRAME_LOCAL_NED
    assert (target.position.x, target.position.y, target.position.z) == (1.25, -0.5, 1.1)
    assert target.yaw == 0.75
    assert target.type_mask & DummyPositionTarget.IGNORE_VX
    assert target.type_mask & DummyPositionTarget.IGNORE_AFX
    assert target.type_mask & DummyPositionTarget.IGNORE_YAW_RATE

    plan_module = load_module("stage7_flight_plan", args.plan_module)
    plan = plan_module.build_plan(json.loads(args.config.read_text(encoding="utf-8")))
    navigation_actions = [
        action for action in plan["actions"] if action["stage"] == "collaborative_navigate"
    ]
    assert [action["action"] for action in navigation_actions] == [
        "publish_planner_goal",
        "publish_planner_goal",
        "verify_planned_navigation",
        "verify_planned_navigation",
    ]
    for action in navigation_actions[2:]:
        assert action["planner_cmd_topic"].startswith(f"/{action['uav']}/planning/")
        assert action["mavros_odom_topic"].startswith(f"/{action['uav']}/mavros/")
        assert action["tolerance_m"] == 0.3

    sys.path.insert(0, str(args.executor_module.parent))
    executor = load_module("mission_executor_stage7", args.executor_module)
    executor.validate_plan(plan)
    events = executor._events_for_action(
        navigation_actions[2],
        {
            "status": "ros_navigation_success",
            "detail": "goal reached",
            "navigation": {"distance_m": 0.12, "planner_commands": 42},
        },
        executor.EventClock(),
    )
    assert any(event["event"] == "navigation_confirmed" for event in events)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
