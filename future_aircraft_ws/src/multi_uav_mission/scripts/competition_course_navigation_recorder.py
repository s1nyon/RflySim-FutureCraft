#!/usr/bin/env python3
"""Read-only run-scoped evidence recorder for UAV1 Section A navigation.

This process subscribes only.  Course truth is used to define evaluation ROIs;
it is never published and cannot influence mission or planner decisions.
"""

from __future__ import annotations

import argparse
import json
import math
import threading
import time
from pathlib import Path

from competition_course_geometry import load_spec, validate_spec
from competition_course_navigation_plan import world_to_local_xy


ROI_FRAME_ID = "uav1_camera_init"


def _stamp_seconds(message):
    stamp = message.header.stamp
    return float(stamp.secs) + float(stamp.nsecs) * 1e-9


def _local_point(world, spawn, yaw_deg):
    xy = world_to_local_xy(world[:2], spawn, yaw_deg)
    return [xy[0], xy[1], float(world[2]) - float(spawn[2])]


def _bounds(points, margin_m):
    return {
        "minimum_local": [min(point[index] for point in points) - margin_m for index in range(3)],
        "maximum_local": [max(point[index] for point in points) + margin_m for index in range(3)],
    }


def build_roi_regions(spec, margin_m=0.2):
    """Derive local-frame evaluation ROIs from the authoritative map spec."""
    validate_spec(spec)
    spawn = spec["spawns"]["uav1"]
    yaw_deg = spec["spawn_yaw_deg"]["uav1"]
    regions = {}
    for obstacle in spec["static_obstacles"]:
        if obstacle.get("segment") != "section_a":
            continue
        center, size = obstacle["center"], obstacle["size"]
        yaw = math.radians(float(obstacle.get("yaw_deg", 0.0)))
        corners = []
        for sx in (-0.5, 0.5):
            for sy in (-0.5, 0.5):
                for sz in (-0.5, 0.5):
                    dx, dy = sx * float(size[0]), sy * float(size[1])
                    world = [
                        float(center[0]) + math.cos(yaw) * dx - math.sin(yaw) * dy,
                        float(center[1]) + math.sin(yaw) * dx + math.cos(yaw) * dy,
                        float(center[2]) + sz * float(size[2]),
                    ]
                    corners.append(_local_point(world, spawn, yaw_deg))
        region = _bounds(corners, float(margin_m))
        # Reject the horizontal floor return at the obstacle base; the side and
        # top surfaces remain inside this evaluation-only ROI.
        center_local = _local_point(center, spawn, yaw_deg)
        region["minimum_local"][2] = max(
            region["minimum_local"][2],
            center_local[2] - float(size[2]) / 2.0 + 0.05,
        )
        region.update({
            "frame": "uav1_local",
            "source": "spec_static_geometry",
            "center_local": center_local,
        })
        regions[obstacle["name"]] = region

    dynamic = spec["dynamic_obstacle"]
    pivot, size = dynamic["pivot"], dynamic["size"]
    amplitude = math.radians(float(dynamic["amplitude_deg"]))
    lateral = float(dynamic["length_m"]) * math.sin(amplitude)
    low_z = float(pivot[2]) - float(dynamic["length_m"])
    high_z = float(pivot[2]) - float(dynamic["length_m"]) * math.cos(amplitude)
    corners = []
    for y in (float(pivot[1]) - lateral - float(size[1]) / 2.0,
              float(pivot[1]) + lateral + float(size[1]) / 2.0):
        for x in (float(pivot[0]) - float(size[0]) / 2.0,
                  float(pivot[0]) + float(size[0]) / 2.0):
            for z in (low_z - float(size[2]) / 2.0, high_z + float(size[2]) / 2.0):
                corners.append(_local_point([x, y, z], spawn, yaw_deg))
    region = _bounds(corners, float(margin_m))
    region.update({
        "frame": "uav1_local",
        "source": "spec_dynamic_sweep_envelope",
        "center_local": [
            (region["minimum_local"][index] + region["maximum_local"][index]) / 2.0
            for index in range(3)
        ],
    })
    regions[dynamic["name"]] = region
    return regions


def summarize_roi_points(points, regions):
    """Count and centroid XYZ points in each axis-aligned evaluation ROI."""
    accumulators = {name: {"count": 0, "sum": [0.0, 0.0, 0.0]} for name in regions}
    for raw_point in points:
        point = [float(value) for value in raw_point[:3]]
        for name, region in regions.items():
            if all(
                float(region["minimum_local"][index]) <= point[index] <= float(region["maximum_local"][index])
                for index in range(3)
            ):
                accumulator = accumulators[name]
                accumulator["count"] += 1
                for index in range(3):
                    accumulator["sum"][index] += point[index]
    result = {}
    for name, accumulator in accumulators.items():
        count = accumulator["count"]
        centroid = [round(value / count, 6) for value in accumulator["sum"]] if count else None
        result[name] = {"point_count": count, "centroid_local": centroid}
    return result


def uav2_state_event(*, armed, mode, connected, receive_monotonic, receive_wall_time):
    return {
        "kind": "uav2_state_sample",
        "receive_monotonic": float(receive_monotonic),
        "receive_wall_time": float(receive_wall_time),
        "armed": bool(armed),
        "mode": str(mode),
        "connected": bool(connected),
    }


def odom_event(message, *, receive_monotonic, receive_wall_time):
    position = message.pose.pose.position
    velocity = message.twist.twist.linear
    return {
        "kind": "uav1_odom",
        "receive_monotonic": float(receive_monotonic),
        "receive_wall_time": float(receive_wall_time),
        "header_stamp_sec": _stamp_seconds(message),
        "frame_id": str(message.header.frame_id),
        "position_local": [float(position.x), float(position.y), float(position.z)],
        "velocity_local": [float(velocity.x), float(velocity.y), float(velocity.z)],
        "speed_mps": math.sqrt(float(velocity.x) ** 2 + float(velocity.y) ** 2 + float(velocity.z) ** 2),
    }


def planner_command_event(message, *, receive_monotonic, receive_wall_time):
    position, velocity, acceleration = message.position, message.velocity, message.acceleration
    return {
        "kind": "planner_command",
        "receive_monotonic": float(receive_monotonic),
        "receive_wall_time": float(receive_wall_time),
        "header_stamp_sec": _stamp_seconds(message),
        "frame_id": str(message.header.frame_id),
        "position_local": [float(position.x), float(position.y), float(position.z)],
        "velocity_local": [float(velocity.x), float(velocity.y), float(velocity.z)],
        "velocity_norm_mps": math.sqrt(float(velocity.x) ** 2 + float(velocity.y) ** 2 + float(velocity.z) ** 2),
        "acceleration_local": [float(acceleration.x), float(acceleration.y), float(acceleration.z)],
        "acceleration_norm_mps2": math.sqrt(
            float(acceleration.x) ** 2 + float(acceleration.y) ** 2 + float(acceleration.z) ** 2
        ),
        "yaw": float(message.yaw),
        "yaw_dot": float(message.yaw_dot),
        "trajectory_id": int(message.trajectory_id),
        "trajectory_flag": int(message.trajectory_flag),
    }


def position_target_event(message, *, receive_monotonic, receive_wall_time):
    position = message.position
    velocity = message.velocity
    acceleration = message.acceleration_or_force
    return {
        "kind": "mavros_position_target",
        "receive_monotonic": float(receive_monotonic),
        "receive_wall_time": float(receive_wall_time),
        "header_stamp_sec": _stamp_seconds(message),
        "frame_id": str(message.header.frame_id),
        "coordinate_frame": int(message.coordinate_frame),
        "type_mask": int(message.type_mask),
        "position_local": [float(position.x), float(position.y), float(position.z)],
        "velocity_local": [float(velocity.x), float(velocity.y), float(velocity.z)],
        "acceleration_or_force_local": [
            float(acceleration.x),
            float(acceleration.y),
            float(acceleration.z),
        ],
        "yaw": float(message.yaw),
        "yaw_rate": float(message.yaw_rate),
        "velocity_ignored": bool(message.type_mask & (8 | 16 | 32)),
        "acceleration_ignored": bool(message.type_mask & (64 | 128 | 256)),
        "force_enabled": bool(message.type_mask & 512),
    }


def bspline_event(message, *, receive_monotonic, receive_wall_time):
    return {
        "kind": "ego_bspline",
        "receive_monotonic": float(receive_monotonic),
        "receive_wall_time": float(receive_wall_time),
        "drone_id": int(message.drone_id),
        "order": int(message.order),
        "traj_id": int(message.traj_id),
        "start_time_sec": float(message.start_time.secs) + float(message.start_time.nsecs) * 1e-9,
        "knot_count": len(message.knots),
        "pos_pts": [
            [float(point.x), float(point.y), float(point.z)]
            for point in message.pos_pts
        ],
        "yaw_pt_count": len(message.yaw_pts),
        "yaw_dt": float(message.yaw_dt),
    }


def validate_cloud_frame(frame_id, expected_frame_ids):
    """Return True only when the cloud frame is one of the declared ROI frames."""
    return str(frame_id) in set(expected_frame_ids)


def run_ros(args, spec):
    import rospy
    from mavros_msgs.msg import State
    from mavros_msgs.msg import PositionTarget
    from geometry_msgs.msg import PoseStamped
    from nav_msgs.msg import Odometry
    from quadrotor_msgs.msg import PositionCommand
    from traj_utils.msg import Bspline
    from sensor_msgs import point_cloud2
    from sensor_msgs.msg import PointCloud2

    regions = build_roi_regions(spec, args.roi_margin_m)
    expected_frames = tuple(args.roi_frame_ids)
    lock = threading.Lock()
    latest_uav2 = {"message": None}
    last_cloud = {"monotonic": -math.inf}

    args.output.parent.mkdir(parents=True, exist_ok=True)
    output = args.output.open("w", encoding="utf-8")

    def write_event(event):
        with lock:
            output.write(json.dumps(event, sort_keys=True) + "\n")
            output.flush()

    def on_odom(message):
        write_event(odom_event(
            message,
            receive_monotonic=time.monotonic(),
            receive_wall_time=time.time(),
        ))

    def on_planner(message):
        write_event(planner_command_event(
            message,
            receive_monotonic=time.monotonic(),
            receive_wall_time=time.time(),
        ))

    def on_position_target(message):
        write_event(position_target_event(
            message,
            receive_monotonic=time.monotonic(),
            receive_wall_time=time.time(),
        ))

    def on_bspline(message):
        write_event(bspline_event(
            message,
            receive_monotonic=time.monotonic(),
            receive_wall_time=time.time(),
        ))

    def on_goal(message):
        position = message.pose.position
        write_event({
            "kind": "planner_goal",
            "receive_monotonic": time.monotonic(),
            "receive_wall_time": time.time(),
            "header_stamp_sec": _stamp_seconds(message),
            "frame_id": str(message.header.frame_id),
            "position_local": [float(position.x), float(position.y), float(position.z)],
        })

    def on_uav2(message):
        latest_uav2["message"] = message
        event = uav2_state_event(
            armed=message.armed, mode=message.mode, connected=message.connected,
            receive_monotonic=time.monotonic(), receive_wall_time=time.time(),
        )
        event["kind"] = "uav2_state_observation"
        write_event(event)

    def sample_uav2(_timer_event):
        message = latest_uav2["message"]
        now_mono, now_wall = time.monotonic(), time.time()
        if message is None:
            write_event(uav2_state_event(
                armed=False, mode="UNAVAILABLE", connected=False,
                receive_monotonic=now_mono, receive_wall_time=now_wall,
            ))
            return
        write_event(uav2_state_event(
            armed=message.armed, mode=message.mode, connected=message.connected,
            receive_monotonic=now_mono, receive_wall_time=now_wall,
        ))

    def on_cloud(message):
        now = time.monotonic()
        if now - last_cloud["monotonic"] < float(args.cloud_interval_s):
            return
        last_cloud["monotonic"] = now
        frame_id = str(message.header.frame_id)
        frame_valid = validate_cloud_frame(frame_id, expected_frames)
        event = {
            "kind": "registered_cloud_roi",
            "receive_monotonic": now,
            "receive_wall_time": time.time(),
            "cloud_frame_id": frame_id,
            "expected_roi_frame_ids": list(expected_frames),
            "roi_evaluation_valid": frame_valid,
        }
        if frame_valid:
            points = point_cloud2.read_points(message, field_names=("x", "y", "z"), skip_nans=True)
            event["regions"] = summarize_roi_points(points, regions)
        else:
            event["regions"] = {
                name: {"point_count": 0, "centroid_local": None}
                for name in regions
            }
            event["roi_evaluation_invalid_reason"] = "ROI_EVALUATION_INVALID_FRAME"
        write_event(event)

    rospy.init_node("competition_course_v2_navigation_recorder", anonymous=True)
    write_event({
        "kind": "recorder_started",
        "receive_monotonic": time.monotonic(),
        "receive_wall_time": time.time(),
        "runtime_decision_source": "lidar_driven",
        "evaluation_truth_used": True,
        "truth_must_not_feed_control": True,
        "regions": regions,
        "roi_frame_contract": {
            "expected_cloud_frame_ids": list(expected_frames),
            "note": "ROI coordinates are uav1_local (spawn-origin ENU); accepted cloud frames are the FAST-LIO world frames tied to uav1_odom by the launch static TF.",
        },
    })
    rospy.Subscriber("/uav1/mavros/local_position/odom", Odometry, on_odom, queue_size=100)
    rospy.Subscriber("/uav1/planning/pos_cmd", PositionCommand, on_planner, queue_size=100)
    rospy.Subscriber("/uav1/mavros/setpoint_raw/local", PositionTarget, on_position_target, queue_size=100)
    rospy.Subscriber("/drone_0_planning/bspline", Bspline, on_bspline, queue_size=10)
    rospy.Subscriber("/uav1/planning/goal", PoseStamped, on_goal, queue_size=10)
    rospy.Subscriber("/uav1/slam/cloud_registered", PointCloud2, on_cloud, queue_size=1)
    rospy.Subscriber("/uav2/mavros/state", State, on_uav2, queue_size=10)
    rospy.Timer(rospy.Duration(float(args.uav2_sample_interval_s)), sample_uav2)
    deadline = time.monotonic() + float(args.duration_s)
    rate = rospy.Rate(20)
    while not rospy.is_shutdown() and time.monotonic() < deadline:
        rate.sleep()
    write_event({"kind": "recorder_stopped", "receive_monotonic": time.monotonic(), "receive_wall_time": time.time()})
    output.close()
    return 0


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--spec", required=True, type=Path)
    parser.add_argument("--output", required=True, type=Path)
    parser.add_argument("--duration-s", type=float, default=600.0)
    parser.add_argument("--uav2-sample-interval-s", type=float, default=0.5)
    parser.add_argument("--cloud-interval-s", type=float, default=0.5)
    parser.add_argument("--roi-margin-m", type=float, default=0.2)
    parser.add_argument("--roi-frame-ids", nargs="+", default=[ROI_FRAME_ID])
    args = parser.parse_args(argv)
    if min(args.duration_s, args.uav2_sample_interval_s, args.cloud_interval_s) <= 0 or args.roi_margin_m < 0:
        parser.error("durations must be positive and ROI margin must be non-negative")
    return run_ros(args, load_spec(args.spec))


if __name__ == "__main__":
    raise SystemExit(main())
