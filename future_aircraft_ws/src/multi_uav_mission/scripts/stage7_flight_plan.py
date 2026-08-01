#!/usr/bin/env python3
"""Build the deterministic Stage 7 dual-UAV live flight plan."""

from __future__ import annotations

import argparse
import json
from pathlib import Path


def build_plan(config):
    uavs = {item["uav_id"]: item for item in config["uavs"]}
    if set(uavs) != {"uav1", "uav2"}:
        raise ValueError("Stage 7 flight plan requires exactly uav1 and uav2")

    takeoff_goals = {
        "uav1": {"x": 0.5, "y": 1.5, "z": 1.0, "yaw": 0.0},
        "uav2": {"x": 1.5, "y": 1.5, "z": 1.0, "yaw": 0.0},
    }
    navigation_goals = {
        "uav1": {"x": 0.7, "y": 1.5, "z": 1.0, "yaw": 0.0},
        "uav2": {"x": 1.7, "y": 1.5, "z": 1.0, "yaw": 0.0},
    }
    actions = []

    def add(stage, action, uav_id=None, **values):
        item = {"sequence": len(actions) + 1, "stage": stage, "action": action}
        if uav_id is not None:
            item["uav"] = uav_id
        item.update(values)
        actions.append(item)

    for uav_id in ("uav1", "uav2"):
        uav = uavs[uav_id]
        add(
            "preflight",
            "wait_for_topics",
            uav_id,
            topics=[uav["mavros_state_topic"], uav["mavros_feedback_odom_topic"]],
            timeout_s=10,
        )
    for uav_id in ("uav1", "uav2"):
        add(
            "preflight",
            "publish_warmup_setpoints",
            uav_id,
            topic=uavs[uav_id]["mavros_setpoint_topic"],
            goal=takeoff_goals[uav_id],
            count=40,
            rate_hz=20,
        )
    for uav_id in ("uav1", "uav2"):
        add(
            "multi_takeoff",
            "call_service",
            uav_id,
            service=uavs[uav_id]["mavros_set_mode_service"],
            request={"custom_mode": "OFFBOARD"},
            timeout_s=10,
        )
    for uav_id in ("uav1", "uav2"):
        add(
            "multi_takeoff",
            "call_service",
            uav_id,
            service=uavs[uav_id]["mavros_arming_service"],
            request={"value": True},
            timeout_s=10,
        )
    for uav_id in ("uav1", "uav2"):
        add(
            "multi_takeoff",
            "publish_position_setpoint",
            uav_id,
            topic=uavs[uav_id]["mavros_setpoint_topic"],
            goal=takeoff_goals[uav_id],
            timeout_s=8,
            rate_hz=20,
        )
    for uav_id in ("uav1", "uav2"):
        add(
            "collaborative_navigate",
            "publish_planner_goal",
            uav_id,
            topic=uavs[uav_id]["planner_goal_topic"],
            goal=navigation_goals[uav_id],
            timeout_s=5,
        )
    for uav_id in ("uav1", "uav2"):
        add(
            "collaborative_navigate",
            "verify_planned_navigation",
            uav_id,
            planner_cmd_topic=uavs[uav_id]["planner_cmd_topic"],
            mavros_odom_topic=uavs[uav_id]["mavros_feedback_odom_topic"],
            goal=navigation_goals[uav_id],
            tolerance_m=0.3,
            timeout_s=30,
        )
    for uav_id in ("uav1", "uav2"):
        add(
            "aruco_landing",
            "call_service",
            uav_id,
            service=uavs[uav_id]["mavros_set_mode_service"],
            request={"custom_mode": "AUTO.LAND"},
            fallback_goal={"z": 0.0},
            timeout_s=30,
        )
    add("mission_report", "write_score_report", score_output="score_summary.json", timeout_s=1)
    return {"mission_name": "stage7_live_slam_ego_swarm_flight", "actions": actions}


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--config", required=True, type=Path)
    parser.add_argument("--output", required=True, type=Path)
    args = parser.parse_args(argv)
    config = json.loads(args.config.read_text(encoding="utf-8"))
    plan = build_plan(config)
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(plan, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
