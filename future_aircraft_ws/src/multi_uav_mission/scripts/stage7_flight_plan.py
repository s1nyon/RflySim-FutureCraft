#!/usr/bin/env python3
"""Build the deterministic Stage 7 dual-UAV live flight plan."""

from __future__ import annotations

import argparse
import json
import math
from pathlib import Path


def _directed_arc_sweep(start_angle, end_angle, turn):
    if turn == "left":
        return (end_angle - start_angle) % (2.0 * math.pi)
    if turn == "right":
        return -((start_angle - end_angle) % (2.0 * math.pi))
    raise ValueError("arc turn must be left or right")


def _sample_centreline(course, target_spacing_m=2.0):
    centreline = course["centreline"]
    if not centreline:
        raise ValueError("course flight requires a non-empty centreline")
    if target_spacing_m <= 0.0:
        raise ValueError("target spacing must be positive")

    segments = []
    total_length = 0.0
    for item in centreline:
        start = tuple(float(value) for value in item["start"])
        end = tuple(float(value) for value in item["end"])
        if item["kind"] == "line":
            length = math.hypot(end[0] - start[0], end[1] - start[1])
            segment = {"kind": "line", "start": start, "end": end, "length": length}
        elif item["kind"] == "arc":
            center = tuple(float(value) for value in item["center"])
            radius = float(item["radius"])
            start_angle = math.atan2(start[1] - center[1], start[0] - center[0])
            end_angle = math.atan2(end[1] - center[1], end[0] - center[0])
            sweep = _directed_arc_sweep(start_angle, end_angle, item["turn"])
            length = abs(sweep) * radius
            segment = {
                "kind": "arc",
                "center": center,
                "radius": radius,
                "start_angle": start_angle,
                "sweep": sweep,
                "length": length,
            }
        else:
            raise ValueError("centreline segment kind must be line or arc")
        if length <= 0.0:
            raise ValueError("centreline segments must have positive length")
        total_length += length
        segments.append(segment)

    interval_count = max(1, int(math.ceil(total_length / target_spacing_m)))
    interval_length = total_length / interval_count
    samples = []
    for sample_index in range(interval_count + 1):
        distance = min(total_length, sample_index * interval_length)
        traversed = 0.0
        for segment_index, segment in enumerate(segments):
            is_last = segment_index == len(segments) - 1
            if distance <= traversed + segment["length"] or is_last:
                ratio = min(1.0, max(0.0, (distance - traversed) / segment["length"]))
                if segment["kind"] == "line":
                    start = segment["start"]
                    end = segment["end"]
                    point = [
                        start[0] + ratio * (end[0] - start[0]),
                        start[1] + ratio * (end[1] - start[1]),
                    ]
                else:
                    angle = segment["start_angle"] + ratio * segment["sweep"]
                    point = [
                        segment["center"][0] + segment["radius"] * math.cos(angle),
                        segment["center"][1] + segment["radius"] * math.sin(angle),
                    ]
                samples.append(point)
                break
            traversed += segment["length"]
    return samples


def _course_routes(course):
    poses = {item["name"]: item["position"] for item in course["takeoff_poses"]}
    platforms = course["landing_platforms"]
    if set(poses) != {"uav1", "uav2"} or len(platforms) < 2:
        raise ValueError("course flight requires uav1/uav2 poses and two landing platforms")
    world_waypoints = _sample_centreline(course)
    routes = {}
    for index, uav_id in enumerate(("uav1", "uav2")):
        origin = poses[uav_id]
        destination = platforms[index]["center"]
        points = world_waypoints + [destination[:2]]
        routes[uav_id] = [
            {
                "x": float(point[0]) - float(origin[0]),
                "y": float(point[1]) - float(origin[1]),
                "z": 1.0,
                "yaw": 0.0,
            }
            for point in points
        ]
    return routes


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
        navigation_routes = _course_routes(course)
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
        def publish_goal(uav_id, goal):
            add(
                "collaborative_navigate",
                "publish_planner_goal",
                uav_id,
                topic=uavs[uav_id]["planner_goal_topic"],
                goal=goal,
                timeout_s=5,
            )

        def verify_goal(uav_id, goal, tolerance_m=0.5):
            add(
                "collaborative_navigate",
                "verify_planned_navigation",
                uav_id,
                planner_cmd_topic=uavs[uav_id]["planner_cmd_topic"],
                mavros_odom_topic=uavs[uav_id]["mavros_feedback_odom_topic"],
                goal=goal,
                tolerance_m=tolerance_m,
                timeout_s=45,
            )

        shared_count = len(navigation_routes["uav1"]) - 1
        publish_goal("uav1", navigation_routes["uav1"][0])
        verify_goal("uav1", navigation_routes["uav1"][0])
        for index in range(1, shared_count):
            publish_goal("uav1", navigation_routes["uav1"][index])
            publish_goal("uav2", navigation_routes["uav2"][index - 1])
            verify_goal("uav1", navigation_routes["uav1"][index])
            verify_goal("uav2", navigation_routes["uav2"][index - 1])

        publish_goal("uav1", navigation_routes["uav1"][-1])
        publish_goal("uav2", navigation_routes["uav2"][shared_count - 1])
        verify_goal("uav1", navigation_routes["uav1"][-1], tolerance_m=0.2)
        verify_goal("uav2", navigation_routes["uav2"][shared_count - 1])
        publish_goal("uav2", navigation_routes["uav2"][-1])
        verify_goal("uav2", navigation_routes["uav2"][-1], tolerance_m=0.2)
    for uav_id in ("uav1", "uav2"):
        platform_goal = {"z": 0.0}
        if course is not None:
            platform_goal.update(
                x=navigation_routes[uav_id][-1]["x"],
                y=navigation_routes[uav_id][-1]["y"],
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
