#!/usr/bin/env python3
"""Focused contract checks for the read-only V2 navigation recorder."""

import importlib.util
import json
import math
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
SCRIPT = ROOT / "future_aircraft_ws/src/multi_uav_mission/scripts/competition_course_navigation_recorder.py"
SPEC = ROOT / "config/maps/competition_course_v2.json"


def load_module():
    assert SCRIPT.exists(), "V2 navigation recorder module is missing"
    sys.path.insert(0, str(SCRIPT.parent))
    spec = importlib.util.spec_from_file_location("competition_course_navigation_recorder", SCRIPT)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def main():
    module = load_module()
    course = json.loads(SPEC.read_text(encoding="utf-8"))
    regions = module.build_roi_regions(course, margin_m=0.2)
    assert set(regions) == {"static_box_a", "moving_pendulum"}

    static = regions["static_box_a"]
    assert static["source"] == "spec_static_geometry"
    assert static["frame"] == "uav1_local"
    assert math.isclose(static["center_local"][0], 4.5, abs_tol=1e-9)
    assert math.isclose(static["center_local"][1], 1.3, abs_tol=1e-9)

    dynamic = regions["moving_pendulum"]
    assert dynamic["source"] == "spec_dynamic_sweep_envelope"
    assert dynamic["minimum_local"][1] < 0.7 < dynamic["maximum_local"][1]
    assert dynamic["minimum_local"][2] < 1.2 < dynamic["maximum_local"][2]

    points = [
        (4.5, 1.3, 0.45),
        (6.0, 0.7, 1.2),
        (100.0, 100.0, 100.0),
    ]
    summary = module.summarize_roi_points(points, regions)
    assert summary["static_box_a"]["point_count"] == 1
    assert summary["static_box_a"]["centroid_local"] == [4.5, 1.3, 0.45]
    assert summary["moving_pendulum"]["point_count"] == 1

    event = module.uav2_state_event(
        armed=False,
        mode="MANUAL",
        connected=True,
        receive_monotonic=10.5,
        receive_wall_time=20.5,
    )
    assert event == {
        "kind": "uav2_state_sample",
        "receive_monotonic": 10.5,
        "receive_wall_time": 20.5,
        "armed": False,
        "mode": "MANUAL",
        "connected": True,
    }

    source = SCRIPT.read_text(encoding="utf-8")
    assert "rospy.Publisher" not in source
    assert "rospy.ServiceProxy" not in source
    assert "/uav2/planning" not in source
    print("competition_course_v2_navigation_recorder_check: PASS")


if __name__ == "__main__":
    main()
