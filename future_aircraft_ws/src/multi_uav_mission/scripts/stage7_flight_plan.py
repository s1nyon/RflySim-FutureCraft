#!/usr/bin/env python3
"""Build the deterministic Stage 7 dual-UAV live flight plan."""

from __future__ import annotations

import argparse
import json
import math
from pathlib import Path

import course_guidance


LOOKAHEAD_STRAIGHT_M = 2.2
LOOKAHEAD_TURN_M = 0.9


def build_plan(config, course=None):
    uavs = {item["uav_id"]: item for item in config["uavs"]}
    if set(uavs) != {"uav1", "uav2"}:
        raise ValueError("Stage 7 flight plan requires exactly uav1 and uav2")

    geofence = None
    if course is None:
        takeoff_goals = {
            "uav1": {"x": 0.5, "y": 1.5, "z": 1.0, "yaw": 0.0},
            "uav2": {"x": 1.5, "y": 1.5, "z": 1.0, "yaw": 0.0},
        }
        navigation_routes = {
            "uav1": [{"x": 0.7, "y": 1.5, "z": 1.0, "yaw": 0.0}],
            "uav2": [{"x": 1.7, "y": 1.5, "z": 1.0, "yaw": 0.0}],
        }
        mission_name = "stage7_live_slam_ego_swarm_flight"
    else:
        takeoff_goals = {
            "uav1": {"x": 0.0, "y": 0.0, "z": 1.0, "yaw": 0.0},
            "uav2": {"x": 0.0, "y": 0.0, "z": 1.0, "yaw": 0.0},
        }
        mission_name = "stage8_predicted_course_tunnel_flight"
        geofence = {
            "min_x": -1.1, "max_x": 17.0,
            "min_y": -2.0, "max_y": 7.0,
            "min_z": -0.5, "max_z": 2.0,
            "max_speed_mps": 2.0, "max_odom_age_s": 0.5,
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
    if course is None:
        for uav_id in ("uav1", "uav2"):
            goal = navigation_routes[uav_id][0]
            add(
                "collaborative_navigate",
                "publish_planner_goal",
                uav_id,
                topic=uavs[uav_id]["planner_goal_topic"],
                goal=goal,
                timeout_s=5,
            )
        for uav_id in ("uav1", "uav2"):
            goal = navigation_routes[uav_id][0]
            add(
                "collaborative_navigate",
                "verify_planned_navigation",
                uav_id,
                planner_cmd_topic=uavs[uav_id]["planner_cmd_topic"],
                mavros_odom_topic=uavs[uav_id]["mavros_feedback_odom_topic"],
                goal=goal,
                tolerance_m=0.3,
                timeout_s=30,
            )
    else:
        centreline = course_guidance.Centreline.from_course(course)
        gates = course_guidance.build_flythrough_gates(
            course,
            lookahead_straight=LOOKAHEAD_STRAIGHT_M,
            lookahead_turn=LOOKAHEAD_TURN_M,
        )
        poses = {item["name"]: item["position"] for item in course["takeoff_poses"]}
        platforms = course["landing_platforms"]

        def local_goal(uav_id, point, z=1.0):
            origin = poses[uav_id]
            return {
                "x": float(point[0]) - float(origin[0]),
                "y": float(point[1]) - float(origin[1]),
                "z": z,
                "yaw": 0.0,
            }

        def publish_goal(uav_id, goal, **meta):
            add(
                "collaborative_navigate",
                "publish_planner_goal",
                uav_id,
                topic=uavs[uav_id]["planner_goal_topic"],
                goal=goal,
                timeout_s=5,
                **meta,
            )

        def verify_goal(uav_id, goal, tolerance_m, **meta):
            add(
                "collaborative_navigate",
                "verify_planned_navigation",
                uav_id,
                planner_cmd_topic=uavs[uav_id]["planner_cmd_topic"],
                mavros_odom_topic=uavs[uav_id]["mavros_feedback_odom_topic"],
                goal=goal,
                tolerance_m=tolerance_m,
                timeout_s=meta.pop("timeout_s", 45),
                **meta,
            )

        gap_s = 1.5
        leader_entries = []
        follower_entries = []
        last_follower_s = -math.inf
        for phase, gate in enumerate(gates):
            leader_entries.append(
                {
                    "phase": phase,
                    "checkpoint_s": gate["s"],
                    "target_s": gate["target_s"],
                    "lookahead_m": gate["target_s"] - gate["s"],
                    "segment_kind": centreline.kind_at_s(gate["s"]),
                    "width": centreline.width_at_s(gate["s"]),
                    "checkpoint": gate["checkpoint"],
                    "target": gate["target"],
                }
            )
            follower_s = gate["s"] - gap_s
            if follower_s >= -1e-9:
                follower_gate = course_guidance.gate_at_or_before(gates, follower_s)
                if follower_gate is not None and follower_gate["s"] > last_follower_s + 1e-9:
                    follower_entries.append(
                        {
                            "phase": phase,
                            "leader_checkpoint_s": gate["s"],
                            "checkpoint_s": follower_gate["s"],
                            "target_s": follower_gate["target_s"],
                            "lookahead_m": follower_gate["target_s"] - follower_gate["s"],
                            "segment_kind": centreline.kind_at_s(follower_gate["s"]),
                            "width": centreline.width_at_s(follower_gate["s"]),
                            "checkpoint": follower_gate["checkpoint"],
                            "target": follower_gate["target"],
                        }
                    )
                    last_follower_s = follower_gate["s"]

        follower_by_phase = {entry["phase"]: entry for entry in follower_entries}
        # Leader-first scheduling: the leader's next look-ahead target is
        # published immediately after its own checkpoint verification, BEFORE
        # any follower verification can block forward progress.  Checkpoint
        # verification uses along-track course_s progress (injected by the
        # executor from plan["course_guidance"]), so a late verify still
        # confirms once the vehicle has passed the gate.
        for index, leader in enumerate(leader_entries):
            if index == 0:
                publish_goal(
                    "uav1",
                    local_goal("uav1", leader["target"]),
                    checkpoint_s=leader["checkpoint_s"],
                    target_s=leader["target_s"],
                    lookahead_m=leader["lookahead_m"],
                    segment_kind=leader["segment_kind"],
                    width=leader["width"],
                    phase=leader["phase"],
                    terminal=False,
                )
            verify_goal(
                "uav1",
                local_goal("uav1", leader["checkpoint"]),
                0.1,
                checkpoint_s=leader["checkpoint_s"],
                phase=leader["phase"],
                terminal=False,
            )
            if index + 1 < len(leader_entries):
                nxt = leader_entries[index + 1]
                publish_goal(
                    "uav1",
                    local_goal("uav1", nxt["target"]),
                    checkpoint_s=nxt["checkpoint_s"],
                    target_s=nxt["target_s"],
                    lookahead_m=nxt["lookahead_m"],
                    segment_kind=nxt["segment_kind"],
                    width=nxt["width"],
                    phase=nxt["phase"],
                    terminal=False,
                )
            follower = follower_by_phase.get(leader["phase"])
            if follower is not None:
                publish_goal(
                    "uav2",
                    local_goal("uav2", follower["target"]),
                    checkpoint_s=follower["checkpoint_s"],
                    target_s=follower["target_s"],
                    lookahead_m=follower["lookahead_m"],
                    segment_kind=follower["segment_kind"],
                    width=follower["width"],
                    phase=follower["phase"],
                    leader_checkpoint_s=follower["leader_checkpoint_s"],
                    terminal=False,
                )
                verify_goal(
                    "uav2",
                    local_goal("uav2", follower["checkpoint"]),
                    0.1,
                    checkpoint_s=follower["checkpoint_s"],
                    phase=follower["phase"],
                    terminal=False,
                )

        platform_local = {
            "uav1": local_goal("uav1", platforms[0]["center"][:2]),
            "uav2": local_goal("uav2", platforms[1]["center"][:2]),
        }
        for uav_id in ("uav1", "uav2"):
            publish_goal(uav_id, platform_local[uav_id], terminal=True)
        for uav_id in ("uav1", "uav2"):
            verify_goal(uav_id, platform_local[uav_id], 0.2, terminal=True)
    for uav_id in ("uav1", "uav2"):
        platform_goal = {"z": 0.0}
        if course is not None:
            platform_goal.update(
                x=platform_local[uav_id]["x"],
                y=platform_local[uav_id]["y"],
            )
        add(
            "aruco_landing",
            "call_service",
            uav_id,
            service=uavs[uav_id]["mavros_set_mode_service"],
            request={"custom_mode": "AUTO.LAND"},
            fallback_goal=platform_goal,
            timeout_s=30,
        )
    add("mission_report", "write_score_report", score_output="score_summary.json", timeout_s=1)
    plan = {"mission_name": mission_name, "actions": actions}
    if geofence is not None:
        plan["geofence"] = geofence
    if course is not None:
        plan["course_guidance"] = {
            "centreline": course["centreline"],
            "takeoff_poses": course["takeoff_poses"],
        }
    return plan


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--config", required=True, type=Path)
    parser.add_argument("--course-spec", type=Path)
    parser.add_argument("--output", required=True, type=Path)
    args = parser.parse_args(argv)
    config = json.loads(args.config.read_text(encoding="utf-8"))
    course = None
    if args.course_spec is not None:
        course = json.loads(args.course_spec.read_text(encoding="utf-8"))
    plan = build_plan(config, course)
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(plan, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
