#!/usr/bin/env python3
"""Contract checks for the Stage 8 hard geofence."""

from __future__ import annotations

import argparse
import importlib.util
import sys
from pathlib import Path


def load_module(path: Path, name: str):
    spec = importlib.util.spec_from_file_location(name, path)
    if spec is None or spec.loader is None:
        raise RuntimeError(f"cannot load geofence module: {path}")
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--module", required=True, type=Path)
    parser.add_argument("--watchdog", required=True, type=Path)
    args = parser.parse_args()
    module = load_module(args.module, "course_geofence")
    watchdog = load_module(args.watchdog, "course_geofence_watchdog")
    fence = module.Geofence(min_x=0.0, max_x=10.0, min_y=-2.0, max_y=2.0, min_z=0.2, max_z=2.0)

    assert module.validate_point((5.0, 0.0, 1.0), fence) is True
    assert module.validate_segment((1.0, 0.0, 1.0), (9.0, 0.0, 1.0), fence) is True
    try:
        module.validate_point((10.1, 0.0, 1.0), fence)
    except module.GeofenceViolation:
        pass
    else:
        raise AssertionError("out-of-bounds point was accepted")
    try:
        module.validate_segment((1.0, 0.0, 1.0), (11.0, 0.0, 1.0), fence)
    except module.GeofenceViolation:
        pass
    else:
        raise AssertionError("out-of-bounds segment was accepted")

    assert module.watchdog_decision((5.0, 0.0, 1.0), fence, armed=True, mode="OFFBOARD", odom_age_s=0.1, speed_mps=0.2) == "continue"
    # Wildly unreasonable positions must not trigger AUTO.LAND.
    assert module.watchdog_decision((5.0, 0.0, 20.0), fence, armed=True, mode="OFFBOARD", odom_age_s=0.1, speed_mps=0.2) == "no_autoland"
    assert module.watchdog_decision((50.0, 0.0, 1.0), fence, armed=True, mode="OFFBOARD", odom_age_s=0.1, speed_mps=0.2) == "no_autoland"
    assert module.watchdog_decision((5.0, 30.0, 1.0), fence, armed=True, mode="OFFBOARD", odom_age_s=0.1, speed_mps=0.2) == "no_autoland"
    # Slightly outside the geofence stays a normal land trigger.
    assert module.watchdog_decision((10.2, 0.0, 1.0), fence, armed=True, mode="OFFBOARD", odom_age_s=0.1, speed_mps=0.2) == "land"
    # The unreasonable margin is configurable per fence.
    wide = module.Geofence(
        min_x=0.0, max_x=10.0, min_y=-2.0, max_y=2.0, min_z=0.2, max_z=2.0,
        unreasonable_margin_m=20.0,
    )
    assert module.watchdog_decision((25.0, 0.0, 1.0), wide, armed=True, mode="OFFBOARD", odom_age_s=0.1, speed_mps=0.2) == "land"
    assert module.watchdog_decision((50.0, 0.0, 1.0), wide, armed=True, mode="OFFBOARD", odom_age_s=0.1, speed_mps=0.2) == "no_autoland"
    assert module.watchdog_decision(
        (5.0, 0.0, 1.0),
        fence,
        armed=True,
        mode="ALTCTL",
        odom_age_s=0.1,
        speed_mps=0.2,
        mode_grace_active=True,
    ) == "continue"
    assert module.watchdog_decision((5.0, 0.0, 1.0), fence, armed=True, mode="ALTCTL", odom_age_s=0.1, speed_mps=0.2) == "land"
    assert module.watchdog_decision((5.0, 0.0, 1.0), fence, armed=True, mode="OFFBOARD", odom_age_s=1.1, speed_mps=0.2) == "land"
    assert module.watchdog_decision((5.0, 0.0, 1.0), fence, armed=True, mode="OFFBOARD", odom_age_s=0.1, speed_mps=4.0) == "land"
    uav1_node = watchdog.watchdog_node_name("/uav1/mavros/state")
    uav2_node = watchdog.watchdog_node_name("/uav2/mavros/state")
    assert uav1_node == "course_geofence_watchdog_uav1"
    assert uav2_node == "course_geofence_watchdog_uav2"
    assert uav1_node != uav2_node
    armed_since = watchdog.next_armed_since(None, armed=True, now=10.0)
    assert armed_since == 10.0
    assert watchdog.next_armed_since(armed_since, armed=True, now=11.0) == 10.0
    assert watchdog.mode_grace_active(armed_since, now=11.9, grace_s=2.0) is True
    assert watchdog.mode_grace_active(armed_since, now=12.0, grace_s=2.0) is False
    assert watchdog.next_armed_since(armed_since, armed=False, now=11.0) is None
    print("stage8 geofence: PASS")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
