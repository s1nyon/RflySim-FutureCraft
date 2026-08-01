#!/usr/bin/env python3
"""Contract check for the Stage 7 FAST-LIO odometry frame relay."""

from __future__ import annotations

import argparse
import copy
import importlib.util
from pathlib import Path
from types import SimpleNamespace


def load_relay(module_path: Path):
    spec = importlib.util.spec_from_file_location("odom_frame_relay", str(module_path))
    if spec is None or spec.loader is None:
        raise RuntimeError(f"cannot load relay module: {module_path}")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def make_dummy_odom():
    return SimpleNamespace(
        header=SimpleNamespace(frame_id="camera_init", stamp="stamp0", seq=42),
        child_frame_id="body",
        pose=SimpleNamespace(
            pose=SimpleNamespace(position=[1.0, 2.0, 3.0], orientation=[0.0, 0.0, 0.0, 1.0]),
            covariance=list(range(36)),
        ),
        twist=SimpleNamespace(
            twist=SimpleNamespace(linear=[0.1, 0.2, 0.3], angular=[0.0, 0.0, 0.1]),
            covariance=list(range(36, 72)),
        ),
    )


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--module", required=True)
    args = parser.parse_args()

    relay = load_relay(Path(args.module))
    original = make_dummy_odom()
    before = copy.deepcopy(original)

    rewritten = relay.rewrite_odometry_frames(
        original,
        frame_id="uav1_camera_init",
        child_frame_id="uav1_body",
    )

    assert rewritten is not original, "relay must return a copied odometry message"
    assert rewritten.header.frame_id == "uav1_camera_init"
    assert rewritten.child_frame_id == "uav1_body"
    assert original.header.frame_id == before.header.frame_id
    assert original.child_frame_id == before.child_frame_id
    assert rewritten.header.stamp == before.header.stamp
    assert rewritten.pose == before.pose
    assert rewritten.twist == before.twist
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
