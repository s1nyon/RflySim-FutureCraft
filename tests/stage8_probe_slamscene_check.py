#!/usr/bin/env python3
"""SLAMScene course-aware parameters for the dynamic-wall LiDAR probe."""

from __future__ import annotations

import argparse
import importlib.util
import sys
from pathlib import Path


def load_module(module_path: Path):
    spec = importlib.util.spec_from_file_location("stage8_dynamic_lidar_probe", module_path)
    if spec is None or spec.loader is None:
        raise RuntimeError(f"cannot load module from {module_path}")
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--module", type=Path, required=True)
    args = parser.parse_args()
    module = load_module(args.module)

    x, y = module.lidar_frame_xy(
        wall_ned=(2.0, 1.5, 0.0),
        sensor_ned=(0.5, 1.5, 0.0),
        yaw_deg=0.0,
    )
    assert (x, y) == (1.5, 0.0)

    x, y = module.lidar_frame_xy(
        wall_ned=(16.0, 0.0, 0.0),
        sensor_ned=(16.0, -0.7, 0.0),
        yaw_deg=0.0,
    )
    assert (x, y) == (0.0, 0.7)

    points = [
        (1.49, 0.0, 0.0),
        (1.55, 0.0, 0.0),
        (1.0, 0.0, 0.0),
    ]
    assert module.count_wall_roi(points, distance_m=1.5) == 2
    assert module.count_wall_roi(points, wall_lidar_x=1.5) == 2, (
        "wall_lidar_x must drive the ROI distance"
    )
    assert module.count_wall_roi(points, wall_lidar_x=2.0) == 0

    geometry = module.capture_geometry(
        sensor_pose_ned=(16.0, -0.7, 0.0),
        sensor_yaw_deg=90.0,
        wall_position_ned=(18.5, 0.0, 0.0),
        sensor_frame="uav1_lidar",
    )
    assert geometry["sensor_frame"] == "uav1_lidar"
    assert geometry["sensor_pose_ned"] == [16.0, -0.7, 0.0]
    assert geometry["wall_position_ned"] == [18.5, 0.0, 0.0]
    assert geometry["wall_lidar_x"] == 0.7
    assert geometry["wall_lidar_y"] == -2.5

    empty = module.capture_geometry(
        sensor_pose_ned=None,
        sensor_yaw_deg=None,
        wall_position_ned=None,
        sensor_frame=None,
    )
    assert empty["wall_lidar_x"] is None
    assert empty["sensor_frame"] is None

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
