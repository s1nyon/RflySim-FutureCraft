#!/usr/bin/env python3
"""Behavior checks for the Stage 8 two-UAV tunnel flight plan."""

from __future__ import annotations

import argparse
import importlib.util
import json
import math
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
        "min_x": -1.1, "max_x": 17.0, "min_y": -2.0, "max_y": 7.0,
        "min_z": -0.5, "max_z": 2.0, "max_speed_mps": 2.0, "max_odom_age_s": 0.5,
    }
    # The failed flight recovered from its -1.057 m takeoff overshoot; it must
    # remain inside the protected envelope instead of forcing AUTO.LAND.
    assert -1.057 > plan["geofence"]["min_x"]
    navigation = [
        action for action in plan["actions"] if action["stage"] == "collaborative_navigate"
    ]
    assert len(navigation) > 28
    publish_actions = [
        action for action in navigation if action["action"] == "publish_planner_goal"
    ]
    verify_actions = [
        action for action in navigation if action["action"] == "verify_planned_navigation"
    ]
    assert len(publish_actions) == len(verify_actions)
    assert [
        (action["uav"], tuple(round(float(action["goal"][axis]), 3) for axis in ("x", "y", "z")))
        for action in publish_actions
    ] == [
        (action["uav"], tuple(round(float(action["goal"][axis]), 3) for axis in ("x", "y", "z")))
        for action in verify_actions
    ]
    uav1_goals = rounded_goals(publish_actions, "uav1")
    uav2_goals = rounded_goals(publish_actions, "uav2")
    assert len(uav1_goals) == len(uav2_goals)
    assert 8 <= len(uav1_goals) <= 10
    assert uav1_goals[-1] == (16.0, 4.6, 1.0)
    assert uav2_goals[-1] == (16.0, 5.2, 1.0)

    poses = {item["name"]: item["position"] for item in course["takeoff_poses"]}
    shared_uav1 = [
        (goal[0] + poses["uav1"][0], goal[1] + poses["uav1"][1])
        for goal in uav1_goals[:-1]
    ]
    shared_uav2 = [
        (goal[0] + poses["uav2"][0], goal[1] + poses["uav2"][1])
        for goal in uav2_goals[:-1]
    ]
    assert all(
        math.hypot(first[0] - second[0], first[1] - second[1]) <= 0.002
        for first, second in zip(shared_uav1, shared_uav2)
    )
    gaps = [
        math.hypot(second[0] - first[0], second[1] - first[1])
        for first, second in zip(shared_uav1, shared_uav1[1:])
    ]
    assert gaps
    assert min(gaps) >= 1.7
    assert max(gaps) <= 2.1

    for uav_id in ("uav1", "uav2"):
        uav_verifies = [action for action in verify_actions if action["uav"] == uav_id]
        assert all(abs(float(action["tolerance_m"]) - 0.5) <= 1e-9 for action in uav_verifies[:-1])
        assert abs(float(uav_verifies[-1]["tolerance_m"]) - 0.2) <= 1e-9

    # UAV1 enters first. Every shared-route cycle then advances UAV1 one
    # sample before sending UAV2 to the sample immediately behind it.
    assert [item["uav"] for item in publish_actions[:3]] == ["uav1", "uav1", "uav2"]
    uav1_shared_index = {goal: index for index, goal in enumerate(uav1_goals[:-1])}
    uav2_shared_index = {goal: index for index, goal in enumerate(uav2_goals[:-1])}
    for index in range(1, len(shared_uav1)):
        leader = next(
            action for action in publish_actions
            if action["uav"] == "uav1"
            and rounded_goals([action], "uav1")[0] == uav1_goals[index]
        )
        follower = next(
            action for action in publish_actions
            if action["uav"] == "uav2"
            and rounded_goals([action], "uav2")[0] == uav2_goals[index - 1]
        )
        assert publish_actions.index(leader) < publish_actions.index(follower)
        assert uav1_shared_index[uav1_goals[index]] - uav2_shared_index[uav2_goals[index - 1]] == 1

    landing = [
        action
        for action in plan["actions"]
        if action["stage"] == "aruco_landing" and action["action"] == "call_service"
    ]
    assert [action["uav"] for action in landing] == ["uav1", "uav2"]
    assert all(action["request"] == {"custom_mode": "AUTO.LAND"} for action in landing)
    expected_landing_goals = {
        "uav1": {"x": 16.0, "y": 4.6, "z": 0.0},
        "uav2": {"x": 16.0, "y": 5.2, "z": 0.0},
    }
    assert all(action["fallback_goal"] == expected_landing_goals[action["uav"]] for action in landing)

    launch = ET.parse(args.dual_launch).getroot()
    launch_args = {item.attrib["name"]: item.attrib.get("default") for item in launch.findall("arg")}
    assert float(launch_args["map_size_x"]) >= 40.0
    assert float(launch_args["map_size_y"]) >= 20.0
    assert float(launch_args["max_vel"]) == 0.45
    assert float(launch_args["max_acc"]) == 0.55
    single_launch = ET.parse(args.dual_launch.with_name("rflysim_ego_swarm_single.launch")).getroot()
    max_jerk = single_launch.find(".//param[@name='manager/max_jerk']")
    assert max_jerk is not None
    assert float(max_jerk.attrib["value"]) == 2.0

    runner = args.dual_launch.parents[4] / "scripts" / "wsl" / "stage7_live_slam_ego_swarm_flight.sh"
    assert runner.read_text(encoding="utf-8").count("--min-x -1.1 --max-x 17") == 2
    print("stage8 course flight plan: PASS")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
