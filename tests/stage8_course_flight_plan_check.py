#!/usr/bin/env python3
"""Behavior checks for the Stage 8 two-UAV tunnel flight plan."""

from __future__ import annotations

import argparse
import importlib.util
import json
from pathlib import Path
import xml.etree.ElementTree as ET


def load_module(path: Path):
    spec = importlib.util.spec_from_file_location("stage8_course_flight_plan", path)
    if spec is None or spec.loader is None:
        raise RuntimeError(f"cannot load flight plan module: {path}")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def rounded_goals(actions, uav_id):
    return [
        tuple(round(float(action["goal"][axis]), 3) for axis in ("x", "y", "z"))
        for action in actions
        if action["action"] == "publish_planner_goal" and action["uav"] == uav_id
    ]


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--plan-module", required=True, type=Path)
    parser.add_argument("--config", required=True, type=Path)
    parser.add_argument("--course-spec", required=True, type=Path)
    parser.add_argument("--dual-launch", required=True, type=Path)
    args = parser.parse_args()

    module = load_module(args.plan_module)
    config = json.loads(args.config.read_text(encoding="utf-8"))
    course = json.loads(args.course_spec.read_text(encoding="utf-8"))
    plan = module.build_plan(config, course)

    assert plan["mission_name"] == "stage8_predicted_course_tunnel_flight"
    assert plan["geofence"] == {
        "min_x": -1.0, "max_x": 17.0, "min_y": -2.0, "max_y": 7.0,
        "min_z": -0.5, "max_z": 2.0, "max_speed_mps": 2.0, "max_odom_age_s": 0.5,
    }
    navigation = [
        action for action in plan["actions"] if action["stage"] == "collaborative_navigate"
    ]
    assert len(navigation) == 28
    for index in range(0, len(navigation), 2):
        publish, verify = navigation[index : index + 2]
        assert publish["action"] == "publish_planner_goal"
        assert verify["action"] == "verify_planned_navigation"
        assert publish["uav"] == verify["uav"]
        assert publish["goal"] == verify["goal"]
    assert [action["uav"] for action in navigation[:14]] == ["uav1"] * 14
    assert [action["uav"] for action in navigation[14:]] == ["uav2"] * 14

    assert rounded_goals(navigation, "uav1") == [
        (2.5, 0.7, 1.0),
        (7.0, 0.7, 1.0),
        (7.9, 1.6, 1.0),
        (7.9, 4.7, 1.0),
        (8.8, 5.6, 1.0),
        (13.3, 5.6, 1.0),
        (16.0, 4.6, 1.0),
    ]
    assert rounded_goals(navigation, "uav2") == [
        (2.5, -0.7, 1.0),
        (7.0, -0.7, 1.0),
        (7.9, 0.2, 1.0),
        (7.9, 3.3, 1.0),
        (8.8, 4.2, 1.0),
        (13.3, 4.2, 1.0),
        (16.0, 5.2, 1.0),
    ]

    landing = [
        action
        for action in plan["actions"]
        if action["stage"] == "aruco_landing" and action["action"] == "call_service"
    ]
    assert [action["uav"] for action in landing] == ["uav1", "uav2"]
    assert all(action["request"] == {"custom_mode": "AUTO.LAND"} for action in landing)

    launch = ET.parse(args.dual_launch).getroot()
    launch_args = {item.attrib["name"]: item.attrib.get("default") for item in launch.findall("arg")}
    assert float(launch_args["map_size_x"]) >= 40.0
    assert float(launch_args["map_size_y"]) >= 20.0
    print("stage8 course flight plan: PASS")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
