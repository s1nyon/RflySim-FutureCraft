#!/usr/bin/env python3
"""Build provenance-labelled UAV1 Section A navigation acceptance reports."""

from __future__ import annotations

import argparse
import json
import math
import statistics
from pathlib import Path
from typing import Any, Dict, Iterable, List, Sequence, Tuple

from competition_course_geometry import build_wall_boxes, load_spec
from competition_course_navigation_plan import local_to_world_xy, world_to_local_xy


REQUIRED_UAV1_EVENTS = (
    "offboard_confirmed",
    "arming_confirmed",
    "takeoff_altitude_confirmed",
    "navigation_confirmed",
    "terminal_settle_confirmed",
    "landing_confirmed",
    "disarm_confirmed",
)
MIN_OBSTACLE_ROI_POINTS = 5
STATIC_SPARSE_MIN_FRAMES = 3
STATIC_CENTROID_ERROR_TOLERANCE_M = 0.5


def _local_point(world, spawn, yaw_deg):
    xy = world_to_local_xy(world[:2], spawn, yaw_deg)
    return [xy[0], xy[1], float(world[2]) - float(spawn[2])]


def _event_present(events: Iterable[Dict[str, Any]], name: str, uav: str = "uav1") -> bool:
    return any(item.get("event") == name and item.get("uav") == uav for item in events)


def _section(spec: Dict[str, Any], name: str) -> Dict[str, Any]:
    matches = [item for item in spec["course"] if item.get("name") == name]
    if len(matches) != 1 or matches[0].get("kind") != "line":
        raise ValueError("report section must name exactly one line")
    return matches[0]


def _line_projection(section: Dict[str, Any], point: Sequence[float]) -> Tuple[float, float]:
    start, end = section["start"], section["end"]
    dx, dy = float(end[0]) - float(start[0]), float(end[1]) - float(start[1])
    length = math.hypot(dx, dy)
    ux, uy = dx / length, dy / length
    rel_x, rel_y = float(point[0]) - float(start[0]), float(point[1]) - float(start[1])
    along = rel_x * ux + rel_y * uy
    cross = abs(rel_x * (-uy) + rel_y * ux)
    return along, cross


def _signed_box_distance(point: Sequence[float], center: Sequence[float], size: Sequence[float], yaw_rad: float) -> float:
    dx, dy = float(point[0]) - float(center[0]), float(point[1]) - float(center[1])
    cosine, sine = math.cos(float(yaw_rad)), math.sin(float(yaw_rad))
    local_x = cosine * dx + sine * dy
    local_y = -sine * dx + cosine * dy
    qx = abs(local_x) - float(size[0]) / 2.0
    qy = abs(local_y) - float(size[1]) / 2.0
    outside = math.hypot(max(qx, 0.0), max(qy, 0.0))
    inside = min(max(qx, qy), 0.0)
    return outside + inside


def _trajectory(plan, spec, recorder_events):
    contract = plan["navigation_contract"]
    spawn = contract["spawn_world_enu"]
    yaw = contract["spawn_yaw_deg"]
    section = _section(spec, contract["section"])
    samples = []
    for item in recorder_events:
        if item.get("kind") != "uav1_odom":
            continue
        local = item["position_local"]
        world_xy = local_to_world_xy(local[:2], spawn, yaw)
        along, cross = _line_projection(section, world_xy)
        samples.append({
            "receive_monotonic": float(item["receive_monotonic"]),
            "local": [float(value) for value in local],
            "world_enu": [world_xy[0], world_xy[1], float(local[2]) + float(spawn[2])],
            "speed_mps": float(item.get("speed_mps", 0.0)),
            "section_s_m": along,
            "section_cross_track_m": cross,
        })
    return samples


def _active_interval(collision_monitor):
    try:
        start = float(collision_monitor["active_start_wall_time"])
        end = float(collision_monitor["active_end_wall_time"])
    except (KeyError, TypeError, ValueError):
        return None
    return (start, end) if end >= start else None


def _uav2_monitor(recorder_events, active_interval):
    samples = [item for item in recorder_events if item.get("kind") == "uav2_state_sample"]
    observations = [item for item in recorder_events if item.get("kind") == "uav2_state_observation"]
    samples.sort(key=lambda item: float(item["receive_monotonic"]))
    intervals = [
        float(second["receive_monotonic"]) - float(first["receive_monotonic"])
        for first, second in zip(samples, samples[1:])
    ]
    violations = [
        {
            "receive_monotonic": float(item["receive_monotonic"]),
            "armed": bool(item.get("armed")),
            "mode": str(item.get("mode", "")),
            "connected": bool(item.get("connected", False)),
        }
        for item in samples + observations
        if (bool(item.get("armed")) or str(item.get("mode", "")) == "OFFBOARD"
            or not bool(item.get("connected", False)))
    ]

    def state(item):
        if item is None:
            return None
        return {
            "receive_monotonic": float(item["receive_monotonic"]),
            "receive_wall_time": float(item["receive_wall_time"]),
            "armed": bool(item.get("armed")),
            "mode": str(item.get("mode", "")),
            "connected": bool(item.get("connected", False)),
        }

    covered = False
    if samples and active_interval is not None:
        start, end = active_interval
        wall_times = [float(item["receive_wall_time"]) for item in samples]
        maximum_gap = max((second - first for first, second in zip(wall_times, wall_times[1:])), default=0.0)
        expected_gap = statistics.median(intervals) if intervals else math.inf
        covered = (
            wall_times[0] <= start
            and wall_times[-1] >= end
            and maximum_gap <= max(1.0, 3.0 * expected_gap)
        )
    return {
        "sample_count": len(samples),
        "state_observation_count": len(observations),
        "monitoring_interval_s": round(statistics.median(intervals), 3) if intervals else None,
        "first_state": state(samples[0] if samples else None),
        "final_state": state(samples[-1] if samples else None),
        "violations": violations,
        "covered_active_interval": covered,
    }


def _static_trajectory_evidence(recorder_events, spawn, yaw_deg, spec):
    """Use EGO bspline geometry as independent evidence that static obstacles
    entered the planner map.  The trajectory is evaluation-side evidence only.
    """
    matches = [item for item in spec["static_obstacles"] if item.get("segment") == "section_a"]
    if len(matches) != 1:
        return {"trajectory_evidence": False}
    obstacle = matches[0]
    center_local = _local_point(obstacle["center"], spawn, yaw_deg)
    size = [float(value) for value in obstacle["size"]]
    bsplines = [
        item for item in recorder_events
        if item.get("kind") == "ego_bspline" and isinstance(item.get("pos_pts"), list)
    ]
    if not bsplines:
        return {"trajectory_evidence": False}
    points = [point for item in bsplines for point in item["pos_pts"]]
    x_values = [float(point[0]) for point in points]
    zone_covered = max(x_values) >= float(center_local[0]) + size[0] / 2.0
    signed = [
        _signed_box_distance(
            (float(point[0]), float(point[1])),
            center_local[:2],
            size[:2],
            0.0,
        )
        for point in points
    ]
    minimum = min(signed)
    return {
        "trajectory_evidence": True,
        "trajectory_covers_obstacle_zone": zone_covered,
        "minimum_signed_distance_m": round(minimum, 4),
        "avoids_static_obstacle": zone_covered and minimum > 0.0,
    }


def _perception(recorder_events, spawn, yaw_deg, spec):
    roi_events = [item for item in recorder_events if item.get("kind") == "registered_cloud_roi"]
    invalid_frames = [
        str(item.get("cloud_frame_id"))
        for item in roi_events
        if item.get("roi_evaluation_valid") is not True
    ]
    static_counts = []
    static_centroids = []
    dynamic_centroids = []
    dynamic_counts = []
    expected_frames = []
    static_center_local = None
    static_matches = [item for item in spec["static_obstacles"] if item.get("segment") == "section_a"]
    if len(static_matches) == 1:
        static_center_local = _local_point(static_matches[0]["center"], spawn, yaw_deg)
    for item in roi_events:
        expected = item.get("expected_roi_frame_ids")
        if isinstance(expected, list):
            expected_frames.extend(str(value) for value in expected)
        regions = item.get("regions", {})
        static = regions.get("static_box_a", {})
        dynamic = regions.get("moving_pendulum", {})
        static_count = int(static.get("point_count", 0))
        static_counts.append(static_count)
        if static_count > 0 and static.get("centroid_local") is not None:
            static_centroids.append(tuple(float(value) for value in static["centroid_local"]))
        dynamic_counts.append(int(dynamic.get("point_count", 0)))
        if int(dynamic.get("point_count", 0)) >= MIN_OBSTACLE_ROI_POINTS and dynamic.get("centroid_local") is not None:
            dynamic_centroids.append(tuple(float(value) for value in dynamic["centroid_local"]))
    maximum_shift = 0.0
    for first in dynamic_centroids:
        for second in dynamic_centroids:
            maximum_shift = max(maximum_shift, math.sqrt(sum((a - b) ** 2 for a, b in zip(first, second))))
    roi_valid = not invalid_frames and bool(roi_events)
    trajectory_evidence = _static_trajectory_evidence(recorder_events, spawn, yaw_deg, spec)
    frames_with_points = sum(1 for value in static_counts if value >= 1)
    total_points = sum(static_counts)
    centroid_error = None
    if static_center_local is not None and static_centroids:
        centroid_error = min(
            math.dist(
                static_center_local[:2],
                [float(value) for value in centroid[:2]],
            )
            for centroid in static_centroids
        )
    static_registered_cloud_observed = bool(
        roi_valid
        and frames_with_points >= STATIC_SPARSE_MIN_FRAMES
        and (
            centroid_error is None
            or centroid_error <= STATIC_CENTROID_ERROR_TOLERANCE_M
        )
    )
    planner_avoidance_consistent = bool(
        trajectory_evidence.get("trajectory_evidence")
        and trajectory_evidence.get("avoids_static_obstacle")
    )
    return {
        "source": "faster_lio_registered_cloud_evaluation_roi",
        "minimum_roi_points": MIN_OBSTACLE_ROI_POINTS,
        "static_sparse_min_frames": STATIC_SPARSE_MIN_FRAMES,
        "static_centroid_error_tolerance_m": STATIC_CENTROID_ERROR_TOLERANCE_M,
        "roi_evaluation_valid": roi_valid,
        "cloud_frame_ids_observed": sorted(set(str(item.get("cloud_frame_id")) for item in roi_events)),
        "expected_roi_frame_ids": sorted(set(expected_frames)),
        "roi_evaluation_invalid_frames": sorted(set(invalid_frames)),
        "static_roi_frame_valid": roi_valid,
        "static_registered_cloud_observed": static_registered_cloud_observed,
        "static_obstacle_frames_observed": frames_with_points,
        "static_obstacle_max_points": max(static_counts) if static_counts else 0,
        "static_obstacle_total_points": total_points,
        "static_obstacle_centroid_error": (
            round(centroid_error, 4) if centroid_error is not None else None
        ),
        "planner_avoidance_consistent": planner_avoidance_consistent,
        "planner_min_signed_distance_to_static_obstacle": (
            trajectory_evidence.get("minimum_signed_distance_m")
            if trajectory_evidence.get("trajectory_evidence")
            else None
        ),
        "planner_obstacle_region_coverage": (
            trajectory_evidence.get("trajectory_covers_obstacle_zone")
            if trajectory_evidence.get("trajectory_evidence")
            else False
        ),
        "static_trajectory_evidence": trajectory_evidence,
        "dynamic_obstacle_observed": any(value >= MIN_OBSTACLE_ROI_POINTS for value in dynamic_counts),
        "dynamic_centroid_shift_m": round(maximum_shift, 3),
        "dynamic_temporal_change_observed": maximum_shift >= 0.1,
        "frame_count": len(roi_events),
    }


def _percentile(values, fraction):
    if not values:
        return None
    ordered = sorted(values)
    index = (len(ordered) - 1) * float(fraction)
    lower = int(math.floor(index))
    upper = int(math.ceil(index))
    if lower == upper:
        return ordered[lower]
    return ordered[lower] + (ordered[upper] - ordered[lower]) * (index - lower)


def _planner_chain_metrics(recorder_events, max_velocity_mps, max_acceleration_mps2):
    commands = [
        item for item in recorder_events
        if item.get("kind") == "planner_command"
        and item.get("velocity_norm_mps") is not None
        and item.get("acceleration_norm_mps2") is not None
    ]
    velocities = [float(item["velocity_norm_mps"]) for item in commands]
    accelerations = [float(item["acceleration_norm_mps2"]) for item in commands]
    velocity_limit = float(max_velocity_mps)
    acceleration_limit = float(max_acceleration_mps2)
    return {
        "sample_count": len(commands),
        "configured_max_velocity_mps": round(velocity_limit, 4),
        "configured_max_acceleration_mps2": round(acceleration_limit, 4),
        "max_desired_velocity_mps": round(max(velocities), 4) if velocities else None,
        "p95_desired_velocity_mps": round(_percentile(velocities, 0.95), 4) if velocities else None,
        "velocity_over_limit_count": sum(value > velocity_limit + 1e-9 for value in velocities),
        "max_desired_acceleration_mps2": round(max(accelerations), 4) if accelerations else None,
        "acceleration_over_limit_count": sum(value > acceleration_limit + 1e-9 for value in accelerations),
    }


def _control_chain_metrics(recorder_events):
    targets = [item for item in recorder_events if item.get("kind") == "mavros_position_target"]
    if not targets:
        return {
            "sample_count": 0,
            "type_mask_seen": [],
            "coordinate_frames_seen": [],
            "velocity_ignored_consistent": None,
            "acceleration_ignored_consistent": None,
            "force_enabled_consistent": None,
            "control_contract": "NO_POSITION_TARGET_EVIDENCE",
        }
    masks = sorted({int(item["type_mask"]) for item in targets})
    frames = sorted({int(item["coordinate_frame"]) for item in targets})
    velocity_ignored = [bool(item.get("velocity_ignored")) for item in targets]
    acceleration_ignored = [bool(item.get("acceleration_ignored")) for item in targets]
    force_enabled = [bool(item.get("force_enabled")) for item in targets]
    position_only = all(velocity_ignored) and all(acceleration_ignored)
    return {
        "sample_count": len(targets),
        "type_mask_seen": masks,
        "coordinate_frames_seen": frames,
        "velocity_ignored_consistent": len(set(velocity_ignored)) == 1,
        "velocity_ignored": bool(velocity_ignored[0]),
        "acceleration_ignored_consistent": len(set(acceleration_ignored)) == 1,
        "acceleration_ignored": bool(acceleration_ignored[0]),
        "force_enabled_consistent": len(set(force_enabled)) == 1,
        "force_enabled": bool(force_enabled[0]),
        "control_contract": "CONTROL_CONTRACT_POSITION_ONLY" if position_only else "CONTROL_CONTRACT_WITH_FEEDFORWARD",
    }


def _tracking_metrics(recorder_events, max_match_delta_s=0.1):
    odoms = sorted(
        (
            item for item in recorder_events
            if item.get("kind") == "uav1_odom"
            and item.get("position_local")
            and item.get("receive_wall_time") is not None
        ),
        key=lambda item: float(item["receive_wall_time"]),
    )
    targets = sorted(
        (
            item for item in recorder_events
            if item.get("kind") == "mavros_position_target"
            and item.get("position_local")
            and item.get("receive_wall_time") is not None
        ),
        key=lambda item: float(item["receive_wall_time"]),
    )
    if not odoms or not targets:
        return {"sample_count": 0, "max_position_error_m": None, "p95_position_error_m": None}
    position_errors = []
    for odom in odoms:
        nearest = min(targets, key=lambda item: abs(float(item["receive_wall_time"]) - float(odom["receive_wall_time"])))
        delta = abs(float(nearest["receive_wall_time"]) - float(odom["receive_wall_time"]))
        if delta > float(max_match_delta_s):
            continue
        error = math.dist(
            [float(value) for value in odom["position_local"]],
            [float(value) for value in nearest["position_local"]],
        )
        position_errors.append(error)
    return {
        "sample_count": len(position_errors),
        "note": "numeric as-published comparison; frame semantics (ENU/NED) are resolved in the control-chain RCA",
        "max_position_error_m": round(max(position_errors), 4) if position_errors else None,
        "p95_position_error_m": round(_percentile(position_errors, 0.95), 4) if position_errors else None,
    }


def _clearance_metrics(spec, section, trajectory):
    radius = float(spec["vehicle_envelope"]["horizontal_diameter"]) / 2.0
    active = [sample for sample in trajectory if -1e-9 <= sample["section_s_m"] <= _section_length(section) + 1e-9]
    if not active:
        unavailable = {"value": None, "source_class": "unavailable", "source": "no_section_a_trajectory"}
        return unavailable, unavailable
    walls = build_wall_boxes(spec)
    wall_values = []
    for sample in active:
        point = sample["world_enu"][:2]
        wall_values.extend(
            _signed_box_distance(point, (wall.center.x, wall.center.y), (wall.size.x, wall.size.y), wall.yaw_rad) - radius
            for wall in walls
        )
    static_values = []
    for sample in active:
        point = sample["world_enu"][:2]
        for obstacle in spec["static_obstacles"]:
            static_values.append(
                _signed_box_distance(point, obstacle["center"], obstacle["size"], math.radians(float(obstacle.get("yaw_deg", 0.0)))) - radius
            )
    return (
        {
            "value": round(min(wall_values), 3),
            "source_class": "derived",
            "source": "ros_mavros_odometry+spec_wall_geometry",
        },
        {
            "value": round(min(static_values), 3),
            "source_class": "derived",
            "source": "ros_mavros_odometry+spec_static_geometry",
        },
    )


def _section_length(section):
    return math.hypot(
        float(section["end"][0]) - float(section["start"][0]),
        float(section["end"][1]) - float(section["start"][1]),
    )


def build_report(*, plan, spec, mission_events, recorder_events, flight_events,
                 watchdog_events, collision_monitor, executor_exit_code):
    contract = plan["navigation_contract"]
    section = _section(spec, contract["section"])
    trajectory = _trajectory(plan, spec, recorder_events)
    maximum_s = max((sample["section_s_m"] for sample in trajectory), default=-math.inf)
    passed = [
        item["name"]
        for item in contract["obstacle_regions"]
        if maximum_s + 1e-9 >= float(item["s_end_m"])
    ]
    endpoint_reached = maximum_s + float(_terminal_action(plan)["tolerance_m"]) >= float(contract["along_track_goal_m"])
    progress = {
        "sample_count": len(trajectory),
        "maximum_section_s_m": round(maximum_s, 3) if trajectory else None,
        "terminal_section_s_m": round(float(contract["along_track_goal_m"]), 3),
        "regions_passed": passed,
        "endpoint_reached": endpoint_reached,
        "source_class": "derived",
        "source": "ros_mavros_odometry+spec_section_a",
    }
    active_interval = _active_interval(collision_monitor)
    uav2 = _uav2_monitor(recorder_events, active_interval)
    perception = _perception(
        recorder_events,
        [float(value) for value in contract["spawn_world_enu"]],
        float(contract["spawn_yaw_deg"]),
        spec,
    )
    planner_limits = contract.get("planner_limits", {})
    planner_chain = _planner_chain_metrics(
        recorder_events,
        float(planner_limits.get("max_velocity_mps", 0.0)),
        float(planner_limits.get("max_acceleration_mps2", 0.0)),
    )
    control_chain = _control_chain_metrics(recorder_events)
    tracking = _tracking_metrics(recorder_events)
    wall_clearance, static_clearance = _clearance_metrics(spec, section, trajectory)
    expected_terminal = [float(value) for value in contract["terminal_local"]]
    expected_frame = str(_terminal_action(plan)["goal"]["frame_id"])
    active_goals = []
    if active_interval is not None:
        active_goals = [
            item for item in recorder_events
            if item.get("kind") == "planner_goal"
            and item.get("receive_wall_time") is not None
            and active_interval[0] <= float(item["receive_wall_time"]) <= active_interval[1]
            and str(item.get("frame_id")) == expected_frame
            and len(item.get("position_local", [])) == 3
            and math.dist(
                [float(value) for value in item["position_local"]],
                expected_terminal,
            ) <= 1e-3
        ]
    planner_goal_observed = bool(active_goals)
    goal_wall_time = min(
        (float(item["receive_wall_time"]) for item in active_goals),
        default=None,
    )
    planner_count = sum(
        item.get("kind") == "planner_command"
        and item.get("receive_wall_time") is not None
        and goal_wall_time is not None
        and goal_wall_time <= float(item["receive_wall_time"]) <= active_interval[1]
        for item in recorder_events
    )
    collision_available = False
    if bool(collision_monitor.get("available")) and active_interval is not None:
        try:
            collision_available = (
                float(collision_monitor["monitor_started_wall_time"]) <= active_interval[0]
                and float(collision_monitor["last_heartbeat_wall_time"]) >= active_interval[1]
            )
        except (KeyError, TypeError, ValueError):
            collision_available = False
    if collision_available:
        active_collisions = []
        ignored_collisions = 0
        for item in flight_events:
            if item.get("event") != "collision":
                continue
            timestamp = item.get("timestamp")
            if timestamp is None or active_interval[0] <= float(timestamp) <= active_interval[1]:
                active_collisions.append(item)
            else:
                ignored_collisions += 1
        collision_count = {
            "value": len(active_collisions),
            "source_class": "simulator_evaluation",
            "source": str(collision_monitor.get("source")),
        }
        if ignored_collisions:
            collision_count["ignored_outside_active_interval"] = ignored_collisions
    else:
        collision_count = {
            "value": None,
            "source_class": "unavailable",
            "source": "collision_monitor_interval_not_proven",
        }
    dynamic_clearance = {
        "value": None,
        "source_class": "unavailable",
        "source": "no_time_synchronized_dynamic_entity_pose",
    }
    event_checks = {name: _event_present(mission_events, name) for name in REQUIRED_UAV1_EVENTS}
    goal_accepted = any(
        item.get("event") == "executor_action_success"
        and item.get("action") == "publish_planner_goal"
        and item.get("uav") == "uav1"
        for item in mission_events
    )
    watchdog_trip = any(
        (
            item.get("decision") in ("land", "no_autoland")
            and not (
                item.get("decision") == "land"
                and item.get("reason") == "mode_loss"
                and item.get("mode") == "AUTO.LAND"
            )
        ) or item.get("event") in ("watchdog_trip", "geofence_trip")
        for item in watchdog_events
    )
    offboard_loss = any(
        item.get("event") == "mode_loss"
        and item.get("uav") == "uav1"
        and str(item.get("mode", "")) != "AUTO.LAND"
        for item in flight_events
    )
    failures = []
    if int(executor_exit_code) != 0:
        failures.append("executor_error")
    if not all(event_checks.values()) or not goal_accepted or not planner_goal_observed:
        failures.append("mission_contract")
    if planner_count <= 0:
        failures.append("planner_commands")
    if not endpoint_reached or any(name not in passed for name in contract["expected_obstacle_passage"]):
        failures.append("section_a_progress")
    if uav2["sample_count"] == 0 or uav2["violations"] or not uav2["covered_active_interval"]:
        failures.append("uav2_isolation")
    if watchdog_trip:
        failures.append("watchdog_or_geofence")
    if offboard_loss:
        failures.append("offboard_loss")
    collision_free = wall_clearance["value"] is not None and wall_clearance["value"] >= 0.0
    clearance_threshold = contract.get("navigation_clearance_threshold_m")
    if clearance_threshold is not None:
        clearance_threshold = float(clearance_threshold)
        navigation_clearance_pass = (
            wall_clearance["value"] is not None
            and wall_clearance["value"] >= clearance_threshold
        )
    else:
        navigation_clearance_pass = None
    if not collision_free:
        failures.append("wall_clearance")
    if navigation_clearance_pass is False:
        failures.append("navigation_clearance")
    if static_clearance["value"] is None or static_clearance["value"] < 0.0:
        failures.append("static_obstacle_clearance")
    if contract["expected_obstacle_passage"]:
        if perception["roi_evaluation_valid"] is not True:
            failures.append("obstacle_perception")
        elif (
            not perception["static_registered_cloud_observed"]
            or not perception["dynamic_temporal_change_observed"]
        ):
            failures.append("obstacle_perception")
    if collision_count["value"] is None:
        failures.append("collision_evidence")
    elif collision_count["value"] > 0:
        failures.append("collision")
    failures = list(dict.fromkeys(failures))
    navigation_success = not any(
        reason in failures
        for reason in (
            "executor_error", "mission_contract", "planner_commands", "section_a_progress",
            "uav2_isolation", "watchdog_or_geofence", "offboard_loss", "wall_clearance",
            "navigation_clearance",
            "static_obstacle_clearance", "obstacle_perception", "collision",
        )
    )
    if not failures:
        result = "PASS"
    elif failures == ["collision_evidence"] and navigation_success:
        result = "NAVIGATION_SUCCESS_COLLISION_EVIDENCE_INCOMPLETE"
    else:
        result = "FAIL"
    return {
        "schema_version": 1,
        "mission_name": plan["mission_name"],
        "profile": contract["profile"],
        "map_id": spec["map_id"],
        "spec_sha256": spec["spec_sha256"],
        "ready": not failures,
        "result": result,
        "failure_reasons": failures,
        "runtime_decision_source": "lidar_driven",
        "evaluation_truth_used": True,
        "truth_must_not_feed_control": True,
        "executor_exit_code": int(executor_exit_code),
        "uav1_event_checks": event_checks,
        "planner_goal_accepted": goal_accepted,
        "planner_goal_observed": planner_goal_observed,
        "planner_command_count": planner_count,
        "progress": progress,
        "perception": perception,
        "planner_chain": planner_chain,
        "control_chain": control_chain,
        "tracking": tracking,
        "uav2_monitor": uav2,
        "watchdog_or_geofence_trip": watchdog_trip,
        "unexpected_offboard_loss": offboard_loss,
        "collision_count": collision_count,
        "minimum_wall_clearance_m": wall_clearance,
        "collision_free": collision_free,
        "navigation_clearance_pass": navigation_clearance_pass,
        "wall_clearance_threshold_m": (
            round(clearance_threshold, 4) if clearance_threshold is not None else None
        ),
        "minimum_static_obstacle_clearance_m": static_clearance,
        "dynamic_clearance_m": dynamic_clearance,
    }


def _terminal_action(plan):
    matches = [item for item in plan["actions"] if item.get("action") == "verify_planned_navigation"]
    if len(matches) != 1:
        raise ValueError("V2 plan must contain exactly one terminal verification")
    return matches[0]


def _read_json(path):
    return json.loads(Path(path).read_text(encoding="utf-8"))


def _read_jsonl(path):
    candidate = Path(path)
    if not candidate.exists():
        return []
    return [json.loads(line) for line in candidate.read_text(encoding="utf-8").splitlines() if line.strip()]


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--plan", required=True, type=Path)
    parser.add_argument("--spec", required=True, type=Path)
    parser.add_argument("--mission-events", required=True, type=Path)
    parser.add_argument("--recorder-events", required=True, type=Path)
    parser.add_argument("--flight-events", required=True, type=Path)
    parser.add_argument("--watchdog-events", action="append", default=[], type=Path)
    parser.add_argument("--collision-monitor", required=True, type=Path)
    parser.add_argument("--executor-exit-code", required=True, type=int)
    parser.add_argument("--output", required=True, type=Path)
    args = parser.parse_args(argv)
    watchdog = []
    for path in args.watchdog_events:
        watchdog.extend(_read_jsonl(path))
    report = build_report(
        plan=_read_json(args.plan),
        spec=load_spec(args.spec),
        mission_events=_read_jsonl(args.mission_events),
        recorder_events=_read_jsonl(args.recorder_events),
        flight_events=_read_jsonl(args.flight_events),
        watchdog_events=watchdog,
        collision_monitor=_read_json(args.collision_monitor),
        executor_exit_code=args.executor_exit_code,
    )
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(report, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    print(json.dumps(report, indent=2, sort_keys=True))
    return 0 if report["ready"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
