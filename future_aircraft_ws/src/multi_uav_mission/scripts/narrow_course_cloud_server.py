#!/usr/bin/env python3
"""Publish the predicted narrow-course reference cloud for ROS planners."""

from __future__ import annotations

import argparse
import math
import struct
from pathlib import Path
from typing import Sequence, Tuple

from narrow_course_artifacts import sample_surface_points
from narrow_course_geometry import load_course


Point = Tuple[float, float, float]


def pack_xyz32(points: Sequence[Point]) -> bytes:
    packer = struct.Struct("<fff")
    return b"".join(packer.pack(float(x), float(y), float(z)) for x, y, z in points)


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--spec", type=Path, required=True)
    parser.add_argument("--topic", default="/predicted_narrow_course/global_cloud")
    parser.add_argument("--frame-id", default="world")
    parser.add_argument("--spacing-m", type=float, default=0.1)
    args, ros_args = parser.parse_known_args()
    if not math.isfinite(args.spacing_m) or args.spacing_m <= 0.0:
        raise ValueError("spacing_m must be finite and positive")
    model = load_course(args.spec)
    points = sample_surface_points(model, args.spacing_m)
    if not points:
        raise ValueError("course geometry produced an empty point cloud")
    payload = pack_xyz32(points)

    import rospy  # pylint: disable=import-error,import-outside-toplevel
    from sensor_msgs.msg import PointCloud2, PointField  # pylint: disable=import-error,import-outside-toplevel

    rospy.init_node("predicted_narrow_course_cloud_server", argv=[parser.prog] + ros_args)
    publisher = rospy.Publisher(args.topic, PointCloud2, queue_size=1, latch=True)
    fields = [
        PointField(name="x", offset=0, datatype=PointField.FLOAT32, count=1),
        PointField(name="y", offset=4, datatype=PointField.FLOAT32, count=1),
        PointField(name="z", offset=8, datatype=PointField.FLOAT32, count=1),
    ]
    rate = rospy.Rate(1.0)
    while not rospy.is_shutdown():
        message = PointCloud2()
        message.header.stamp = rospy.Time.now()
        message.header.frame_id = args.frame_id
        message.height = 1
        message.width = len(points)
        message.fields = fields
        message.is_bigendian = False
        message.point_step = 12
        message.row_step = 12 * len(points)
        message.data = payload
        message.is_dense = True
        publisher.publish(message)
        rate.sleep()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
