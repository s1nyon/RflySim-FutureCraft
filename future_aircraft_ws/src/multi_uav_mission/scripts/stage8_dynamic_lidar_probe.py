#!/usr/bin/env python3
"""Probe whether a runtime wall is visible to the TypeID 23 Mid360.

The default flow targets the SLAMScene predicted-narrow-course setup; the wall
center and vehicle pose are expressed in world NED and projected into the
LiDAR frame so the ROI does not depend on stale ChallengeMap coordinates.
"""

from __future__ import annotations

import argparse
import json
import math
import os
from dataclasses import asdict, dataclass
from pathlib import Path
import statistics
import sys
import time
from typing import Dict, Iterable, List, Optional, Sequence, Tuple


Point3 = Tuple[float, float, float]


@dataclass(frozen=True)
class ProbeWall:
    object_id: int
    vehicle_type: int
    position_ned: Point3
    yaw_ned: float
    scale: Point3


def build_probe_wall(
    spawn_ned: Point3 = (0.5, 1.5, 0.0),
    yaw_deg: float = 0.0,
    distance_m: float = 1.5,
) -> ProbeWall:
    if not math.isfinite(distance_m) or distance_m <= 0.0:
        raise ValueError("distance_m must be positive and finite")
    if len(spawn_ned) != 3 or not all(math.isfinite(value) for value in spawn_ned):
        raise ValueError("spawn_ned must contain three finite values")
    yaw_ned = math.radians(yaw_deg)
    return ProbeWall(
        object_id=12999,
        vehicle_type=1000813,
        position_ned=(
            spawn_ned[0] + distance_m * math.cos(yaw_ned),
            spawn_ned[1] + distance_m * math.sin(yaw_ned),
            spawn_ned[2],
        ),
        yaw_ned=yaw_ned,
        scale=(0.2, 4.0, 2.5),
    )


def _wall_kwargs(wall: ProbeWall, window_id: int) -> Dict[str, object]:
    return {
        "copterID": wall.object_id,
        "vehicleType": wall.vehicle_type,
        "MotorRPMSMean": 0,
        "PosE": list(wall.position_ned),
        "AngEuler": [0.0, 0.0, wall.yaw_ned],
        "Scale": list(wall.scale),
        "windowID": window_id,
    }


def place_probe_wall(
    client,
    wall: ProbeWall,
    window_id: int = 0,
    repeat: int = 3,
    delay_s: float = 0.02,
) -> None:
    if repeat < 1:
        raise ValueError("repeat must be positive")
    kwargs = _wall_kwargs(wall, window_id)
    for _attempt in range(repeat):
        client.sendUE4PosScale(**kwargs)
        if delay_s > 0.0:
            time.sleep(delay_s)


def remove_probe_wall(
    client,
    wall: ProbeWall,
    window_id: int = 0,
    repeat: int = 3,
    delay_s: float = 0.02,
) -> None:
    if repeat < 1:
        raise ValueError("repeat must be positive")
    for _attempt in range(repeat):
        client.sendUE4Destroy(wall.object_id, window_id)
        if delay_s > 0.0:
            time.sleep(delay_s)


def count_wall_roi(
    points: Iterable[Point3],
    distance_m: float = 1.5,
    depth_tolerance_m: float = 0.2,
    half_width_m: float = 1.5,
    half_height_m: float = 2.0,
    wall_lidar_x: Optional[float] = None,
) -> int:
    if wall_lidar_x is not None:
        distance_m = abs(float(wall_lidar_x))
    return sum(
        1
        for x, y, z in points
        if distance_m - depth_tolerance_m <= x <= distance_m + depth_tolerance_m
        and abs(y) <= half_width_m
        and abs(z) <= half_height_m
    )


def lidar_frame_xy(
    wall_ned: Point3,
    sensor_ned: Point3,
    yaw_deg: float,
):
    """Project a world NED wall center into the LiDAR horizontal frame."""
    dx = float(wall_ned[0]) - float(sensor_ned[0])
    dy = float(wall_ned[1]) - float(sensor_ned[1])
    yaw = math.radians(float(yaw_deg))
    x = dx * math.cos(yaw) + dy * math.sin(yaw)
    y = -dx * math.sin(yaw) + dy * math.cos(yaw)
    return round(x, 3), round(y, 3)


def capture_geometry(
    sensor_pose_ned: Optional[Point3],
    sensor_yaw_deg: Optional[float],
    wall_position_ned: Optional[Point3],
    sensor_frame: Optional[str],
) -> Dict[str, object]:
    """Describe the sensor pose and the wall center in the LiDAR frame."""
    if (
        sensor_pose_ned is not None
        and sensor_yaw_deg is not None
        and wall_position_ned is not None
    ):
        wall_lidar_x, wall_lidar_y = lidar_frame_xy(
            wall_position_ned,
            sensor_pose_ned,
            sensor_yaw_deg,
        )
    else:
        wall_lidar_x, wall_lidar_y = None, None
    return {
        "sensor_frame": sensor_frame,
        "sensor_pose_ned": (
            [float(value) for value in sensor_pose_ned]
            if sensor_pose_ned is not None
            else None
        ),
        "sensor_yaw_deg": (
            float(sensor_yaw_deg) if sensor_yaw_deg is not None else None
        ),
        "wall_position_ned": (
            [float(value) for value in wall_position_ned]
            if wall_position_ned is not None
            else None
        ),
        "wall_lidar_x": wall_lidar_x,
        "wall_lidar_y": wall_lidar_y,
    }


def analyze_probe(
    before_counts: Sequence[int],
    wall_counts: Sequence[int],
    after_counts: Sequence[int],
    minimum_added_points: int = 100,
) -> Dict[str, object]:
    if not before_counts or not wall_counts or not after_counts:
        raise ValueError("all three probe phases require at least one frame")
    if minimum_added_points <= 0:
        raise ValueError("minimum_added_points must be positive")
    before = float(statistics.median(before_counts))
    wall = float(statistics.median(wall_counts))
    after = float(statistics.median(after_counts))
    added = wall - before
    removed = wall - after
    recovery_tolerance = max(20.0, minimum_added_points / 2.0)
    return {
        "after_median": after,
        "before_median": before,
        "wall_median": wall,
        "added_points": added,
        "removed_points": removed,
        "minimum_added_points": minimum_added_points,
        "recovery_delta": abs(after - before),
        "dynamic_wall_visible": (
            added >= minimum_added_points
            and removed >= minimum_added_points
            and abs(after - before) <= recovery_tolerance
        ),
    }


def _create_client(rflysim_root: Path):
    api_dir = rflysim_root / "RflySimAPIs" / "RflySimSDK" / "ue"
    if not api_dir.is_dir():
        raise RuntimeError(f"RflySim UE API directory does not exist: {api_dir}")
    sys.path.insert(0, str(api_dir))
    import UE4CtrlAPI  # pylint: disable=import-error,import-outside-toplevel

    return UE4CtrlAPI.UE4CtrlAPI()


def _wall_receipt(action: str, wall: ProbeWall, dry_run: bool) -> Dict[str, object]:
    return {
        "action": action,
        "arming_request": False,
        "dry_run": dry_run,
        "map_change": False,
        "wall": asdict(wall),
    }


def _capture_counts(
    topic: str,
    state_topic: str,
    frames: int,
    timeout_s: float,
    *,
    sensor_pose_ned: Optional[Point3] = None,
    sensor_yaw_deg: Optional[float] = None,
    wall_position_ned: Optional[Point3] = None,
    sensor_frame: Optional[str] = None,
) -> Dict[str, object]:
    import rospy
    from mavros_msgs.msg import State
    from sensor_msgs import point_cloud2
    from sensor_msgs.msg import PointCloud2

    if frames < 1:
        raise ValueError("frames must be positive")
    if timeout_s <= 0.0:
        raise ValueError("timeout_s must be positive")
    if not rospy.core.is_initialized():
        rospy.init_node("stage8_dynamic_lidar_probe", anonymous=True)
    state = rospy.wait_for_message(state_topic, State, timeout=timeout_s)
    if state.armed:
        raise RuntimeError(f"refusing LiDAR probe while vehicle is armed: {state_topic}")
    geometry = capture_geometry(
        sensor_pose_ned,
        sensor_yaw_deg,
        wall_position_ned,
        sensor_frame,
    )
    wall_lidar_x = geometry["wall_lidar_x"]
    counts: List[int] = []
    stamps: List[float] = []
    for _index in range(frames):
        cloud = rospy.wait_for_message(topic, PointCloud2, timeout=timeout_s)
        points = point_cloud2.read_points(
            cloud,
            field_names=("x", "y", "z"),
            skip_nans=True,
        )
        counts.append(count_wall_roi(points, wall_lidar_x=wall_lidar_x))
        stamps.append(cloud.header.stamp.to_sec())
    final_state = rospy.wait_for_message(state_topic, State, timeout=timeout_s)
    if final_state.armed:
        raise RuntimeError(f"vehicle armed during LiDAR probe: {state_topic}")
    payload = {
        "armed": False,
        "counts": counts,
        "frames": frames,
        "state_topic": state_topic,
        "stamps": stamps,
        "topic": topic,
    }
    payload.update(geometry)
    return payload


def _read_json(path: Path) -> Dict[str, object]:
    return json.loads(path.read_text(encoding="utf-8"))


def _write_json(path: Path, payload: Dict[str, object]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")


def _add_wall_parser(subparsers) -> None:
    parser = subparsers.add_parser("wall")
    parser.add_argument("--action", choices=("create", "remove"), required=True)
    parser.add_argument("--dry-run", action="store_true")
    parser.add_argument("--window-id", type=int, default=0)
    parser.add_argument("--spawn-ned-x", type=float, default=0.5)
    parser.add_argument("--spawn-ned-y", type=float, default=1.5)
    parser.add_argument("--spawn-ned-z", type=float, default=0.0)
    parser.add_argument("--yaw-deg", type=float, default=0.0)
    parser.add_argument("--distance-m", type=float, default=1.5)
    parser.add_argument("--rflysim-root", type=Path, default=Path(os.environ.get("RFLYSIM_ROOT", r"D:\PX4PSP")))


def _add_capture_parser(subparsers) -> None:
    parser = subparsers.add_parser("capture")
    parser.add_argument("--topic", default="/uav1/rflysim/lidar")
    parser.add_argument("--state-topic", default="/uav1/mavros/state")
    parser.add_argument("--frames", type=int, default=10)
    parser.add_argument("--timeout-s", type=float, default=10.0)
    parser.add_argument("--sensor-pose-ned-x", type=float, default=None)
    parser.add_argument("--sensor-pose-ned-y", type=float, default=None)
    parser.add_argument("--sensor-pose-ned-z", type=float, default=None)
    parser.add_argument("--sensor-yaw-deg", type=float, default=None)
    parser.add_argument("--wall-position-ned-x", type=float, default=None)
    parser.add_argument("--wall-position-ned-y", type=float, default=None)
    parser.add_argument("--wall-position-ned-z", type=float, default=None)
    parser.add_argument("--sensor-frame", default=None)
    parser.add_argument("--output", type=Path, required=True)


def _add_compare_parser(subparsers) -> None:
    parser = subparsers.add_parser("compare")
    parser.add_argument("--before", type=Path, required=True)
    parser.add_argument("--wall", type=Path, required=True)
    parser.add_argument("--after", type=Path, required=True)
    parser.add_argument("--report", type=Path, required=True)
    parser.add_argument("--minimum-added-points", type=int, default=100)


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    subparsers = parser.add_subparsers(dest="command", required=True)
    _add_wall_parser(subparsers)
    _add_capture_parser(subparsers)
    _add_compare_parser(subparsers)
    args = parser.parse_args(argv)

    if args.command == "wall":
        wall = build_probe_wall(
            (args.spawn_ned_x, args.spawn_ned_y, args.spawn_ned_z),
            yaw_deg=args.yaw_deg,
            distance_m=args.distance_m,
        )
        if not args.dry_run:
            client = _create_client(args.rflysim_root)
            if args.action == "create":
                place_probe_wall(client, wall, window_id=args.window_id)
            else:
                remove_probe_wall(client, wall, window_id=args.window_id)
        print(json.dumps(_wall_receipt(args.action, wall, args.dry_run), indent=2, sort_keys=True))
        return 0

    if args.command == "capture":
        payload = _capture_counts(
            args.topic,
            args.state_topic,
            args.frames,
            args.timeout_s,
            sensor_pose_ned=(
                (
                    args.sensor_pose_ned_x,
                    args.sensor_pose_ned_y,
                    args.sensor_pose_ned_z,
                )
                if args.sensor_pose_ned_x is not None
                else None
            ),
            sensor_yaw_deg=args.sensor_yaw_deg,
            wall_position_ned=(
                (
                    args.wall_position_ned_x,
                    args.wall_position_ned_y,
                    args.wall_position_ned_z,
                )
                if args.wall_position_ned_x is not None
                else None
            ),
            sensor_frame=args.sensor_frame,
        )
        _write_json(args.output, payload)
        print(json.dumps(payload, indent=2, sort_keys=True))
        return 0

    before = _read_json(args.before)
    wall_phase = _read_json(args.wall)
    after = _read_json(args.after)
    if any(phase.get("armed") is not False for phase in (before, wall_phase, after)):
        raise RuntimeError("all probe phases must record armed=false")
    analysis = analyze_probe(
        before["counts"],
        wall_phase["counts"],
        after["counts"],
        minimum_added_points=args.minimum_added_points,
    )
    report = {
        "analysis": analysis,
        "arming_request": False,
        "map_change": False,
        "phases": {"after": after, "before": before, "wall": wall_phase},
    }
    _write_json(args.report, report)
    print(json.dumps(report, indent=2, sort_keys=True))
    return 0 if analysis["dynamic_wall_visible"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
