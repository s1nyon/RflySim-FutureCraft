#!/usr/bin/env python3
"""Pure report normalization checks for the read-only V2 live probe."""

import argparse
import json
import sys
import tempfile
from pathlib import Path


def main():
    parser = argparse.ArgumentParser(); parser.add_argument("--project-root", default="."); args = parser.parse_args(); root = Path(args.project_root).resolve()
    sys.path.insert(0, str(root / "future_aircraft_ws/src/multi_uav_mission/scripts"))
    from competition_course_live_probe import build_report, write_reports
    expected = ["/uav1/rflysim/lidar", "/uav1/rflysim/imu", "/uav1/slam/odometry_raw", "/uav1/planning/pos_cmd"]
    samples = {
        expected[0]: [{"arrival": 10.0, "stamp": 9.9, "frame_id": "uav1_lidar", "point_count": 100, "finite_bounds": [0, 1, -1, 1, -1, 1]}],
        expected[1]: [{"arrival": 10.0, "stamp": 9.99, "frame_id": "uav1_imu"}],
        expected[2]: [], expected[3]: [],
    }
    report = build_report(expected, samples, advertised={expected[0], expected[1], expected[2]}, duration=8.0)
    assert report["topics"][expected[0]]["status"] == "OBSERVED"
    assert report["topics"][expected[2]]["status"] == "NO_MESSAGE"
    assert report["topics"][expected[3]]["status"] == "NOT_ADVERTISED"
    assert report["summary"]["topics_observed"] == 2
    assert report["summary"]["topics_missing"] == 2
    with tempfile.TemporaryDirectory() as temp:
        json_path, md_path = write_reports(report, Path(temp))
        assert json.loads(json_path.read_text(encoding="utf-8"))["summary"] == report["summary"]
        assert "NOT_ADVERTISED" in md_path.read_text(encoding="utf-8")
    source = (root / "future_aircraft_ws/src/multi_uav_mission/scripts/competition_course_live_probe.py").read_text(encoding="utf-8")
    for forbidden in ("rospy.Publisher", "rospy.Service", "set_param", "static_transform_publisher", "arming", "set_mode"):
        assert forbidden not in source
    print("competition_course_v2_live_probe_check: PASS")


if __name__ == "__main__": main()
