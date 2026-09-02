#!/usr/bin/env python3
"""Build isolated UAV1 navigation plans from Competition Course V2 truth."""

from __future__ import annotations

import argparse
import json
import math
from pathlib import Path
from typing import Any, Dict, Iterable, List, Sequence, Tuple

from competition_course_geometry import load_spec, validate_spec


def _finite(value: Any, label: str) -> float:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise ValueError("{} must be numeric".format(label))
    result = float(value)
    if not math.isfinite(result):
        raise ValueError("{} must be finite".format(label))
    return result


def _xy(value: Sequence[Any], label: str) -> Tuple[float, float]:
    if not isinstance(value, (list, tuple)) or len(value) < 2:
        raise ValueError("{} must contain x and y".format(label))
    return _finite(value[0], label), _finite(value[1], label)


def world_to_local_xy(point: Sequence[Any], spawn: Sequence[Any], yaw_deg: Any) -> Tuple[float, float]:
    """Apply R(-spawn_yaw) to one world ENU delta."""
    point_x, point_y = _xy(point, "world point")
    spawn_x, spawn_y = _xy(spawn, "spawn")
    yaw = math.radians(_finite(yaw_deg, "spawn yaw"))
    dx, dy = point_x - spawn_x, point_y - spawn_y
    return (
        math.cos(yaw) * dx + math.sin(yaw) * dy,
        -math.sin(yaw) * dx + math.cos(yaw) * dy,
    )


def local_to_world_xy(point: Sequence[Any], spawn: Sequence[Any], yaw_deg: Any) -> Tuple[float, float]:
    """Apply spawn translation and R(spawn_yaw) to one local point."""
    local_x, local_y = _xy(point, "local point")
    spawn_x, spawn_y = _xy(spawn, "spawn")
    yaw = math.radians(_finite(yaw_deg, "spawn yaw"))
    return (
        spawn_x + math.cos(yaw) * local_x - math.sin(yaw) * local_y,
        spawn_y + math.sin(yaw) * local_x + math.cos(yaw) * local_y,
    )


def _section(spec: Dict[str, Any], name: str) -> Dict[str, Any]:
    matches = [item for item in spec["course"] if item.get("name") == name]
    if len(matches) != 1 or matches[0].get("kind") != "line":
        raise ValueError("navigation section must name exactly one line")
    return matches[0]


def _line(section: Dict[str, Any]) -> Tuple[float, float, float]:
    start, end = _xy(section["start"], "section start"), _xy(section["end"], "section end")
    dx, dy = end[0] - start[0], end[1] - start[1]
    length = math.hypot(dx, dy)
    if length <= 0.0:
        raise ValueError("navigation section length must be positive")
    return dx / length, dy / length, length


def _along(section: Dict[str, Any], point: Sequence[Any]) -> float:
    ux, uy, _ = _line(section)
    start = _xy(section["start"], "section start")
    x, y = _xy(point, "section point")
    return (x - start[0]) * ux + (y - start[1]) * uy


def _obstacle_regions(spec: Dict[str, Any], section: Dict[str, Any]) -> List[Dict[str, Any]]:
    regions = []
    ux, uy, _ = _line(section)
    for item in spec["static_obstacles"]:
        if item.get("segment") != section["name"]:
            continue
        size = item["size"]
        half_along = (abs(ux) * float(size[0]) + abs(uy) * float(size[1])) / 2.0
        centre_s = _along(section, item["center"])
        regions.append({
            "name": item["name"],
            "kind": "static",
            "s_start_m": centre_s - half_along,
            "s_end_m": centre_s + half_along,
        })
    dynamic = spec["dynamic_obstacle"]
    if dynamic.get("segment") == section["name"]:
        half_along = (abs(ux) * float(dynamic["size"][0]) + abs(uy) * float(dynamic["size"][1])) / 2.0
        centre_s = _along(section, dynamic["pivot"])
        regions.append({
            "name": dynamic["name"],
            "kind": "dynamic",
            "s_start_m": centre_s - half_along,
            "s_end_m": centre_s + half_along,
        })
    return sorted(regions, key=lambda item: item["s_start_m"])


def _local_geofence(spec: Dict[str, Any], section: Dict[str, Any], spawn, yaw_deg, config) -> Dict[str, float]:
    takeoff = spec["takeoff_area"]["bounds"]
    points = [
        (takeoff[x_index], takeoff[y_index])
        for x_index in (0, 1)
        for y_index in (2, 3)
    ]
    ux, uy, _ = _line(section)
    nx, ny = -uy, ux
    half_width = float(section["width"]) / 2.0
    for endpoint in (section["start"], section["end"]):
        points.append((endpoint[0] + nx * half_width, endpoint[1] + ny * half_width))
        points.append((endpoint[0] - nx * half_width, endpoint[1] - ny * half_width))
    local = [world_to_local_xy(point, spawn, yaw_deg) for point in points]
    margin = _finite(config["horizontal_margin_m"], "geofence horizontal margin")
    return {
        "min_x": min(point[0] for point in local) - margin,
        "max_x": max(point[0] for point in local) + margin,
        "min_y": min(point[1] for point in local) - margin,
        "max_y": max(point[1] for point in local) + margin,
        "min_z": _finite(config["min_z"], "geofence min_z"),
        "max_z": _finite(config["max_z"], "geofence max_z"),
        "max_speed_mps": _finite(config["max_speed_mps"], "geofence max speed"),
        "max_odom_age_s": _finite(config["max_odom_age_s"], "geofence odom age"),
    }


def _validate_navigation_config(config: Dict[str, Any], spec: Dict[str, Any], profile: str) -> Dict[str, Any]:
    if config.get("schema_version") != 1 or config.get("map_id") != spec["map_id"]:
        raise ValueError("navigation config map/schema contract mismatch")
    if config.get("active_uav") != "uav1":
        raise ValueError("V2 navigation baseline active_uav must be uav1")
    profiles = config.get("profiles")
    if not isinstance(profiles, dict) or profile not in profiles:
        raise ValueError("unknown navigation profile: {}".format(profile))
    for label, value in (
        ("flight altitude", config["flight_altitude_m"]),
        ("terminal tolerance", config["terminal"]["tolerance_m"]),
        ("terminal maximum speed", config["terminal"]["maximum_speed_mps"]),
        ("terminal settle duration", config["terminal"]["settle_duration_s"]),
        ("landing timeout", config["landing"]["timeout_s"]),
        ("disarm timeout", config["landing"]["disarm_timeout_s"]),
        ("navigation timeout", profiles[profile]["navigation_timeout_s"]),
    ):
        if _finite(value, label) <= 0.0:
            raise ValueError("{} must be positive".format(label))
    if config["landing"].get("require_disarmed") is not True:
        raise ValueError("V2 landing must require disarm")
    if float(config["landing"]["disarm_timeout_s"]) > float(config["landing"]["timeout_s"]):
        raise ValueError("disarm timeout must not exceed landing timeout")
    planner_limits = config.get("planner_limits")
    if not isinstance(planner_limits, dict):
        raise ValueError("navigation config missing planner_limits")
    for label in ("max_velocity_mps", "max_acceleration_mps2"):
        if _finite(planner_limits[label], label) <= 0.0:
            raise ValueError("{} must be positive".format(label))
    clearance = config.get("navigation_clearance")
    if not isinstance(clearance, dict):
        raise ValueError("navigation config missing navigation_clearance")
    if _finite(clearance["min_wall_clearance_m"], "min_wall_clearance_m") <= 0.0:
        raise ValueError("min_wall_clearance_m must be positive")
    return profiles[profile]


def build_plan(live_config: Dict[str, Any], map_spec: Dict[str, Any], nav_config: Dict[str, Any], profile: str) -> Dict[str, Any]:
    validate_spec(map_spec)
    profile_config = _validate_navigation_config(nav_config, map_spec, profile)
    uavs = {item["uav_id"]: item for item in live_config.get("uavs", [])}
    if set(uavs) != {"uav1", "uav2"}:
        raise ValueError("live config must preserve dual infrastructure")
    uav = uavs["uav1"]
    section = _section(map_spec, profile_config["section"])
    ux, uy, length = _line(section)
    regions = _obstacle_regions(map_spec, section)
    if profile == "short_smoke":
        terminal_s = _finite(profile_config["along_track_offset_m"], "short smoke offset")
        if not 0.0 < terminal_s < min(item["s_start_m"] for item in regions):
            raise ValueError("short smoke terminal must be before all Section A obstacles")
    elif profile_config.get("terminal") == "section_end":
        terminal_s = length
    else:
        raise ValueError("full navigation terminal must be section_end")
    start = _xy(section["start"], "section start")
    terminal_world_xy = (start[0] + ux * terminal_s, start[1] + uy * terminal_s)
    spawn = map_spec["spawns"]["uav1"]
    yaw_deg = map_spec["spawn_yaw_deg"]["uav1"]
    terminal_local_xy = world_to_local_xy(terminal_world_xy, spawn, yaw_deg)
    altitude = float(nav_config["flight_altitude_m"])
    terminal_goal = {
        "x": terminal_local_xy[0],
        "y": terminal_local_xy[1],
        "z": altitude,
        "yaw": 0.0,
        "frame_id": nav_config["planner_goal_frame_id"],
    }
    takeoff_goal = {"x": 0.0, "y": 0.0, "z": altitude, "yaw": 0.0}
    actions: List[Dict[str, Any]] = []

    def add(stage: str, action: str, uav_id=None, **values) -> None:
        item = {"sequence": len(actions) + 1, "stage": stage, "action": action}
        if uav_id is not None:
            item["uav"] = uav_id
        item.update(values)
        actions.append(item)

    add("preflight", "wait_for_topics", "uav1", topics=[uav["mavros_state_topic"], uav["mavros_feedback_odom_topic"]], timeout_s=10.0)
    add("preflight", "publish_warmup_setpoints", "uav1", topic=uav["mavros_setpoint_topic"], goal=takeoff_goal, count=int(nav_config["warmup_count"]), rate_hz=float(nav_config["setpoint_rate_hz"]))
    add("takeoff", "call_service", "uav1", service=uav["mavros_set_mode_service"], request={"custom_mode": "OFFBOARD"}, timeout_s=10.0)
    add("takeoff", "call_service", "uav1", service=uav["mavros_arming_service"], request={"value": True}, timeout_s=10.0)
    add("takeoff", "publish_position_setpoint", "uav1", topic=uav["mavros_setpoint_topic"], goal=takeoff_goal, timeout_s=float(nav_config["takeoff_timeout_s"]), rate_hz=float(nav_config["setpoint_rate_hz"]))
    add("v2_navigation", "publish_planner_goal", "uav1", topic=uav["planner_goal_topic"], goal=terminal_goal, timeout_s=float(nav_config["planner_goal_timeout_s"]))
    add("terminal_settle", "verify_planned_navigation", "uav1", planner_cmd_topic=uav["planner_cmd_topic"], mavros_odom_topic=uav["mavros_feedback_odom_topic"], goal=terminal_goal, tolerance_m=float(nav_config["terminal"]["tolerance_m"]), maximum_speed_mps=float(nav_config["terminal"]["maximum_speed_mps"]), settle_duration_s=float(nav_config["terminal"]["settle_duration_s"]), timeout_s=float(profile_config["navigation_timeout_s"]))
    add("landing", "call_service", "uav1", service=uav["mavros_set_mode_service"], request={"custom_mode": "AUTO.LAND"}, fallback_goal={"x": terminal_local_xy[0], "y": terminal_local_xy[1], "z": 0.0}, timeout_s=float(nav_config["landing"]["timeout_s"]), require_disarmed=True, disarm_timeout_s=float(nav_config["landing"]["disarm_timeout_s"]))
    add("report", "write_score_report", score_output="score_summary.json", timeout_s=1.0)

    passed = [item["name"] for item in regions if item["s_end_m"] <= terminal_s + 1e-9]
    return {
        "mission_name": "competition_course_v2_uav1_{}".format(profile),
        "actions": actions,
        "geofence": _local_geofence(map_spec, section, spawn, yaw_deg, nav_config["geofence"]),
        "map_contract": {
            "map_id": map_spec["map_id"],
            "spec_sha256": map_spec["spec_sha256"],
            "source": "config/maps/competition_course_v2.json",
            "coordinate_frame": "ENU",
            "shared_world_tf_established": False,
        },
        "navigation_contract": {
            "profile": profile,
            "active_uav": "uav1",
            "section": section["name"],
            "spawn_world_enu": list(spawn),
            "spawn_yaw_deg": float(yaw_deg),
            "along_track_goal_m": terminal_s,
            "section_length_m": length,
            "terminal_world_enu": [terminal_world_xy[0], terminal_world_xy[1], altitude],
            "terminal_local": [terminal_local_xy[0], terminal_local_xy[1], altitude],
            "obstacle_regions": regions,
            "obstacle_regions_before_terminal": passed,
            "expected_obstacle_passage": passed,
            "progress_evidence_only": True,
            "terminal_acceptance": "3d_euclidean_point_goal",
            "planner_limits": {
                "max_velocity_mps": float(nav_config["planner_limits"]["max_velocity_mps"]),
                "max_acceleration_mps2": float(nav_config["planner_limits"]["max_acceleration_mps2"]),
            },
            "navigation_clearance_threshold_m": float(
                nav_config["navigation_clearance"]["min_wall_clearance_m"]
            ),
            "navigation_clearance_source": str(
                nav_config["navigation_clearance"].get("source", "")
            ),
        },
        "evaluation_contract": {
            "runtime_decision_source": "lidar_driven",
            "evaluation_truth_used": False,
            "truth_must_not_feed_control": True,
        },
    }


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--config", required=True, type=Path)
    parser.add_argument("--map-spec", required=True, type=Path)
    parser.add_argument("--navigation-config", required=True, type=Path)
    parser.add_argument("--profile", choices=("short_smoke", "full_section_a"), required=True)
    parser.add_argument("--output", required=True, type=Path)
    args = parser.parse_args(argv)
    live_config = json.loads(args.config.read_text(encoding="utf-8"))
    map_spec = load_spec(args.map_spec)
    nav_config = json.loads(args.navigation_config.read_text(encoding="utf-8"))
    plan = build_plan(live_config, map_spec, nav_config, args.profile)
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(plan, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
