#!/usr/bin/env python3
"""Offline behavior checks for the RViz-only frame adapter."""

from __future__ import annotations

import argparse
import importlib.util
from pathlib import Path
from types import SimpleNamespace


def load_module(module_path: Path):
    spec = importlib.util.spec_from_file_location("rviz_frame_adapter", module_path)
    if spec is None or spec.loader is None:
        raise RuntimeError("cannot load module from {}".format(module_path))
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def stamp(seconds: int, nanoseconds: int):
    return SimpleNamespace(secs=seconds, nsecs=nanoseconds)


def odometry(sequence: int):
    return SimpleNamespace(
        header=SimpleNamespace(stamp=stamp(100 + sequence, sequence), frame_id="uav1_camera_init"),
        pose=SimpleNamespace(
            pose=SimpleNamespace(
                position=SimpleNamespace(x=sequence + 0.1, y=sequence + 0.2, z=sequence + 0.3),
                orientation=SimpleNamespace(x=0.0, y=0.0, z=sequence / 10.0, w=1.0),
            )
        ),
    )


def fake_path():
    return SimpleNamespace(header=SimpleNamespace(stamp=None, frame_id=""), poses=[])


def fake_pose():
    return SimpleNamespace(header=SimpleNamespace(stamp=None, frame_id=""), pose=None)


def fake_marker():
    return SimpleNamespace(
        SPHERE=2,
        ADD=0,
        header=SimpleNamespace(stamp=None, frame_id=""),
        ns="",
        id=-1,
        type=-1,
        action=-1,
        pose=SimpleNamespace(
            position=SimpleNamespace(x=0.0, y=0.0, z=0.0),
            orientation=SimpleNamespace(x=0.0, y=0.0, z=0.0, w=0.0),
        ),
        scale=SimpleNamespace(x=0.0, y=0.0, z=0.0),
        color=SimpleNamespace(r=0.0, g=0.0, b=0.0, a=0.0),
    )


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--module", required=True, type=Path)
    args = parser.parse_args()
    adapter = load_module(args.module)

    # Catches in-place mutation or accidental geometry/stamp changes while relabeling.
    original_stamp = stamp(42, 7)
    marker = SimpleNamespace(
        header=SimpleNamespace(frame_id="world", stamp=original_stamp),
        pose=SimpleNamespace(position=SimpleNamespace(x=1.0, y=2.0, z=3.0)),
        points=[SimpleNamespace(x=4.0, y=5.0, z=6.0)],
        scale=SimpleNamespace(x=0.2, y=0.3, z=0.4),
    )
    normalized = adapter.normalize_marker(marker, "uav1_camera_init")
    assert normalized is not marker
    assert normalized.header.frame_id == "uav1_camera_init"
    assert marker.header.frame_id == "world"
    assert normalized.header.stamp.secs == 42
    assert normalized.header.stamp.nsecs == 7
    assert normalized.pose.position.x == 1.0
    assert normalized.points[0].z == 6.0
    normalized.points[0].z = -1.0
    assert marker.points[0].z == 6.0

    # Catches unbounded memory growth, wrong ordering, and numeric pose rewriting.
    path_builder = adapter.BoundedPath(
        frame_id="uav1_camera_init",
        max_poses=3,
        path_factory=fake_path,
        pose_factory=fake_pose,
    )
    for index in range(5):
        latest = path_builder.append_odometry(odometry(index))
    assert latest.header.frame_id == "uav1_camera_init"
    assert latest.header.stamp.secs == 104
    assert len(latest.poses) == 3
    assert [pose.pose.position.x for pose in latest.poses] == [2.1, 3.1, 4.1]
    assert latest.poses[-1].pose.orientation.z == 0.4
    assert latest.poses[-1].header.frame_id == "uav1_camera_init"

    for invalid in (0, -1):
        try:
            adapter.BoundedPath(
                frame_id="uav1_camera_init",
                max_poses=invalid,
                path_factory=fake_path,
                pose_factory=fake_pose,
            )
        except ValueError:
            pass
        else:
            raise AssertionError("non-positive max_poses must fail closed")

    # Catches display code that substitutes MAVROS/local coordinates or drops the command stamp.
    command = SimpleNamespace(
        header=SimpleNamespace(stamp=stamp(88, 9), frame_id="world"),
        position=SimpleNamespace(x=7.5, y=-1.25, z=1.1),
    )
    command_marker = adapter.position_command_marker(
        command, "uav1_camera_init", marker_factory=fake_marker
    )
    assert command_marker.header.frame_id == "uav1_camera_init"
    assert command_marker.header.stamp.secs == 88
    assert command_marker.pose.position.x == 7.5
    assert command_marker.pose.position.y == -1.25
    assert command_marker.pose.position.z == 1.1
    assert command_marker.pose.orientation.w == 1.0
    assert command_marker.type == command_marker.SPHERE
    assert command_marker.action == command_marker.ADD
    assert command_marker.color.a == 1.0

    print("RViz frame adapter offline checks: PASS")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
