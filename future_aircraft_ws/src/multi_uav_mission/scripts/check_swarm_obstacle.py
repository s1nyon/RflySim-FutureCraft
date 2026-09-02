#!/usr/bin/env python3
"""Verify one UAV is perceived as an obstacle in the other UAV's grid map.

Each UAV runs its own FAST-LIO frame (origin at its takeoff pose), so a UAV's
position in the other UAV's map frame is its local position plus the origin
difference. This script reports whether the leading UAV is inside the trailing
UAV's inflated occupancy map within a radius.
"""

from __future__ import annotations

import argparse
import json
import math
import sys
import time


def relative_position(uav1_local, uav2_local, uav1_origin, uav2_origin):
    """Project uav1's local position into uav2's map frame (ENU)."""
    return tuple(
        round(float(uav1_local[i]) + float(uav1_origin[i]) - float(uav2_origin[i]), 3)
        for i in range(3)
    )


def obstacle_at(map_points, position, radius_m):
    x, y, z = (float(value) for value in position)
    for point in map_points:
        distance = math.sqrt(
            (float(point[0]) - x) ** 2
            + (float(point[1]) - y) ** 2
            + (float(point[2]) - z) ** 2
        )
        if distance <= float(radius_m):
            return True
    return False


def _sample_report(map_points, uav1_in_uav2, radius_m):
    occupied = obstacle_at(map_points, uav1_in_uav2, radius_m)
    return {
        "timestamp": round(time.time(), 3),
        "uav1_in_uav2_frame": list(uav1_in_uav2),
        "obstacle_in_radius": occupied,
        "radius_m": radius_m,
        "map_points": len(map_points),
    }


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--uav1-odom-topic", default="/uav1/mavros/local_position/odom")
    parser.add_argument("--uav2-odom-topic", default="/uav2/mavros/local_position/odom")
    parser.add_argument(
        "--uav2-map-topic",
        default="/uav2/planner/rflysim_ego_swarm_node/grid_map/occupancy_inflate",
    )
    parser.add_argument("--uav1-origin", default="16.0,-0.7,0.0")
    parser.add_argument("--uav2-origin", default="16.0,0.7,0.0")
    parser.add_argument("--radius-m", type=float, default=0.8)
    parser.add_argument("--duration-s", type=float, default=15.0)
    parser.add_argument("--output", required=True, type=argparse.FileType("w"))
    args = parser.parse_args(argv)

    import rospy
    from nav_msgs.msg import Odometry
    from sensor_msgs import point_cloud2
    from sensor_msgs.msg import PointCloud2

    uav1_origin = tuple(float(value) for value in args.uav1_origin.split(","))
    uav2_origin = tuple(float(value) for value in args.uav2_origin.split(","))
    rospy.init_node("future_aircraft_swarm_obstacle_check", anonymous=True)
    uav1_pos = [None]
    uav2_pos = [None]

    def odom_callback(uav_pos, origin):
        def _callback(message):
            position = message.pose.pose.position
            uav_pos[0] = (
                float(position.x),
                float(position.y),
                float(position.z),
            )

        return _callback

    rospy.Subscriber(args.uav1_odom_topic, Odometry, odom_callback(uav1_pos, uav1_origin))
    rospy.Subscriber(args.uav2_odom_topic, Odometry, odom_callback(uav2_pos, uav2_origin))
    rate = rospy.Rate(2.0)
    deadline = time.monotonic() + args.duration_s
    reports = []
    while time.monotonic() < deadline and not rospy.is_shutdown():
        if uav1_pos[0] is not None and uav2_pos[0] is not None:
            rel = relative_position(uav1_pos[0], uav2_pos[0], uav1_origin, uav2_origin)
            try:
                cloud = rospy.wait_for_message(
                    args.uav2_map_topic, PointCloud2, timeout=2.0
                )
                points = [
                    (float(p[0]), float(p[1]), float(p[2]))
                    for p in point_cloud2.read_points(
                        cloud, field_names=("x", "y", "z"), skip_nans=True
                    )
                ]
                reports.append(_sample_report(points, rel, args.radius_m))
            except Exception as exc:
                reports.append(
                    {
                        "timestamp": round(time.time(), 3),
                        "uav1_in_uav2_frame": list(rel),
                        "error": str(exc),
                    }
                )
        rate.sleep()
    args.output.write(json.dumps({"reports": reports}, indent=2, sort_keys=True) + "\n")
    any_obstacle = any(
        report.get("obstacle_in_radius") is True for report in reports
    )
    print(
        json.dumps(
            {
                "uav1_seen_as_obstacle": any_obstacle,
                "samples": len(reports),
            },
            sort_keys=True,
        )
    )
    return 0 if any_obstacle else 1


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
