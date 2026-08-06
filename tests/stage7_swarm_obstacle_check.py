#!/usr/bin/env python3
"""Swarm obstacle check must project the other UAV into this UAV's map frame."""

from __future__ import annotations

import argparse
import importlib.util
import sys
from pathlib import Path


def load_module(name: str, module_path: Path):
    sys.path.insert(0, str(module_path.parent))
    spec = importlib.util.spec_from_file_location(name, str(module_path))
    if spec is None or spec.loader is None:
        raise RuntimeError(f"cannot load module: {module_path}")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--module", required=True, type=Path)
    args = parser.parse_args()
    check = load_module("check_swarm_obstacle", args.module)

    # uav1 ENU origin (16,-0.7), uav2 ENU origin (16,0.7); uav2-frame position of
    # uav1 = uav1_local + (uav1_origin - uav2_origin).
    rel = check.relative_position(
        uav1_local=(1.0, 0.5, 1.0),
        uav2_local=(0.0, 0.0, 1.0),
        uav1_origin=(16.0, -0.7, 0.0),
        uav2_origin=(16.0, 0.7, 0.0),
    )
    assert rel == (1.0, -0.9, 1.0)

    occupied = check.obstacle_at(
        map_points=[(1.0, -0.9, 1.0), (1.0, -0.92, 1.02), (5.0, 5.0, 1.0)],
        position=(1.0, -0.9, 1.0),
        radius_m=0.5,
    )
    assert occupied is True

    clear = check.obstacle_at(
        map_points=[(5.0, 5.0, 1.0)],
        position=(1.0, -0.9, 1.0),
        radius_m=0.5,
    )
    assert clear is False

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
