#!/usr/bin/env python3
"""Flight event recorder must classify mode loss, arming, and odom anomalies."""

from __future__ import annotations

import argparse
import importlib.util
import math
import sys
import tempfile
import json
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
    recorder = load_module("flight_event_recorder", args.module)

    event = recorder.classify_mode_event(
        uav="uav1", prev_mode="OFFBOARD", mode="POSCTL", armed=True, timestamp=1.0
    )
    assert event is not None
    assert event["event"] == "mode_loss"
    assert event["uav"] == "uav1"
    assert event["prev_mode"] == "OFFBOARD"
    assert event["mode"] == "POSCTL"
    assert event["timestamp"] == 1.0

    assert recorder.classify_mode_event(
        "uav1", "OFFBOARD", "OFFBOARD", True, 1.0
    ) is None, "same mode must not emit an event"

    armed = recorder.classify_mode_event(
        "uav1", "MANUAL", "MANUAL", True, 2.0, prev_armed=False
    )
    assert armed is not None and armed["event"] == "arming"
    assert armed["armed"] is True

    anomaly = recorder.detect_odom_anomaly(
        position=(float("nan"), 0.0, 1.0),
        speed_mps=0.0,
        geofence=(-1.0, 17.0, -2.0, 7.0, -0.5, 2.0),
    )
    assert anomaly == "nan_position"

    outside = recorder.detect_odom_anomaly(
        position=(30.0, 0.0, 1.0),
        speed_mps=0.0,
        geofence=(-1.0, 17.0, -2.0, 7.0, -0.5, 2.0),
    )
    assert outside == "outside_geofence"

    fast = recorder.detect_odom_anomaly(
        position=(0.0, 0.0, 1.0),
        speed_mps=5.0,
        geofence=(-1.0, 17.0, -2.0, 7.0, -0.5, 2.0),
        max_speed_mps=2.0,
    )
    assert fast == "max_speed"

    assert (
        recorder.detect_odom_anomaly(
            position=(0.0, 0.0, 1.0),
            speed_mps=0.1,
            geofence=(-1.0, 17.0, -2.0, 7.0, -0.5, 2.0),
            max_speed_mps=2.0,
        )
        is None
    )

    crash = recorder.crash_event(
        copter_id=1,
        crash_type=-1,
        position_ned=(1.0, 2.0, 0.0),
        crash_pos_ned=(1.0, 2.0, 1.0),
        crashed_name="boundary_wall",
        timestamp=3.0,
    )
    assert crash["event"] == "collision"
    assert crash["crash_type"] == -1
    assert crash["crashed_name"] == "boundary_wall"

    with tempfile.TemporaryDirectory() as temp_dir:
        status_path = Path(temp_dir) / "crash_monitor_status.json"
        recorder.write_crash_monitor_status(
            status_path,
            available=True,
            monitor_started_wall_time=4.0,
            last_heartbeat_wall_time=5.0,
        )
        status = json.loads(status_path.read_text(encoding="utf-8"))
        assert status == {
            "available": True,
            "error": None,
            "last_heartbeat_wall_time": 5.0,
            "monitor_started_wall_time": 4.0,
            "source": "rflysim_reqVeCrashData_udp_20006",
        }

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
