#!/usr/bin/env python3
"""Behavior checks for the Stage 8 two-UAV tunnel flight plan.

The continuous-tunnel contract is: intermediate planner targets are
look-ahead points ahead of a fly-through checkpoint (target != checkpoint),
the final landing platform is the only terminal goal, and the follower is
progress-spaced by arc length instead of a fixed waypoint index.
"""

from __future__ import annotations

import argparse
import importlib.util
import json
import math
import sys
from pathlib import Path
import xml.etree.ElementTree as ET


def load_module(path: Path):
    sys.path.insert(0, str(path.parent))
    spec = importlib.util.spec_from_file_location("stage8_course_flight_plan", path)
    if spec is None or spec.loader is None:
        raise RuntimeError(f"cannot load flight plan module: {path}")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def rounded_goal(goal):
    return tuple(round(float(goal[axis]), 3) for axis in ("x", "y", "z"))


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
    assert -1.057 > plan["geofence"]["min_x"]

    navigation = [
        action for action in plan["actions"] if action["stage"] == "collaborative_navigate"
    ]
    publishes = [action for action in navigation if action["action"] == "publish_planner_goal"]
    verifies = [action for action in navigation if action["action"] == "verify_planned_navigation"]

    uav1_publishes = [action for action in publishes if action["uav"] == "uav1"]
    uav2_publishes = [action for action in publishes if action["uav"] == "uav2"]
    uav1_verifies = [action for action in verifies if action["uav"] == "uav1"]
    uav2_verifies = [action for action in verifies if action["uav"] == "uav2"]

    assert len(uav1_publishes) == len(uav1_verifies)
    assert len(uav2_publishes) == len(uav2_verifies)
    assert len(uav1_publishes) > len(uav2_publishes)

    for uav_id in ("uav1", "uav2"):
        pub = (uav1_publishes if uav_id == "uav1" else uav2_publishes)[-1]
        ver = (uav1_verifies if uav_id == "uav1" else uav2_verifies)[-1]
        assert pub.get("terminal") is True
        assert ver.get("terminal") is True
        assert rounded_goal(pub["goal"]) == rounded_goal(ver["goal"])
        assert float(ver["tolerance_m"]) == 0.2

    uav1_int_pub = [action for action in uav1_publishes if action.get("terminal") is not True]
    uav2_int_pub = [action for action in uav2_publishes if action.get("terminal") is not True]
    uav1_int_ver = [action for action in uav1_verifies if action.get("terminal") is not True]
    uav2_int_ver = [action for action in uav2_verifies if action.get("terminal") is not True]

    assert len(uav1_int_pub) == len(uav1_int_ver)
    assert len(uav2_int_pub) == len(uav2_int_ver)
    assert 18 <= len(uav1_int_pub) <= 30
    assert len(uav2_int_pub) < len(uav1_int_pub)
    assert uav1_int_pub[0]["checkpoint_s"] == 0.0

    for pub, ver in zip(uav1_int_pub, uav1_int_ver):
        assert pub["checkpoint_s"] == ver["checkpoint_s"]
        assert pub["target_s"] > pub["checkpoint_s"]
        assert abs((pub["target_s"] - pub["checkpoint_s"]) - pub["lookahead_m"]) <= 1e-9
        assert rounded_goal(pub["goal"]) != rounded_goal(ver["goal"])
        assert float(ver["tolerance_m"]) == 0.5
        if pub["segment_kind"] == "arc":
            assert abs(pub["lookahead_m"] - 1.0) <= 1e-9
        else:
            assert 0.0 < pub["lookahead_m"] <= 2.2 + 1e-9

    for pub, ver in zip(uav2_int_pub, uav2_int_ver):
        assert pub["checkpoint_s"] == ver["checkpoint_s"]
        assert pub["target_s"] > pub["checkpoint_s"]
        assert rounded_goal(pub["goal"]) != rounded_goal(ver["goal"])
        assert float(ver["tolerance_m"]) == 0.5

    assert any(pub["segment_kind"] == "arc" and abs(pub["lookahead_m"] - 1.0) <= 1e-9 for pub in uav1_int_pub)
    assert any(pub["segment_kind"] == "line" and abs(pub["lookahead_m"] - 2.2) <= 1e-9 for pub in uav1_int_pub)

    # Tandem progress spacing: follower checkpoints advance monotonically and
    # stay at least 1.5 m of arc length behind the leader gate that triggered it.
    follower_s = [pub["checkpoint_s"] for pub in uav2_int_pub]
    assert follower_s == sorted(follower_s)
    assert len(set(follower_s)) == len(follower_s)
    for pub in uav2_int_pub:
        assert pub["leader_checkpoint_s"] - pub["checkpoint_s"] >= 1.5 - 1e-9

    # The follower target must never be published ahead of the leader target in
    # arc-length terms for the same phase (it tracks the same corridor offset).
    leader_by_phase = {pub["phase"]: pub for pub in uav1_int_pub}
    for pub in uav2_int_pub:
        leader = leader_by_phase[pub["phase"]]
        assert pub["target_s"] <= leader["target_s"] + 1e-9

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
    assert all(
        rounded_goal(action["fallback_goal"]) == rounded_goal(expected_landing_goals[action["uav"]])
        for action in landing
    )

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
