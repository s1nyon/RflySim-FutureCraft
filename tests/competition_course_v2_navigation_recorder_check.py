#!/usr/bin/env python3
"""Focused contract checks for the read-only V2 navigation recorder."""

import importlib.util
import json
import math
import sys
from pathlib import Path
from types import SimpleNamespace


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
    summary = module.summarize_roi_points(iter(points), regions)
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

    def point(x, y, z):
        return SimpleNamespace(x=x, y=y, z=z)

    def vector(x, y, z):
        return SimpleNamespace(x=x, y=y, z=z)

    def header(stamp_sec=1.0, frame_id="uav1_camera_init"):
        return SimpleNamespace(stamp=SimpleNamespace(secs=int(stamp_sec), nsecs=int((stamp_sec % 1.0) * 1e9)), frame_id=frame_id)

    odom = SimpleNamespace(
        header=header(1.5, "uav1_odom"),
        pose=SimpleNamespace(pose=SimpleNamespace(position=point(2.0, 3.0, 4.0))),
        twist=SimpleNamespace(twist=SimpleNamespace(linear=vector(1.0, 2.0, 2.0))),
    )
    odom_event = module.odom_event(odom, receive_monotonic=30.0, receive_wall_time=40.0)
    assert odom_event["kind"] == "uav1_odom"
    assert odom_event["position_local"] == [2.0, 3.0, 4.0]
    assert odom_event["velocity_local"] == [1.0, 2.0, 2.0]
    assert math.isclose(odom_event["speed_mps"], 3.0, abs_tol=1e-9)
    assert odom_event["frame_id"] == "uav1_odom"
    assert math.isclose(odom_event["header_stamp_sec"], 1.5, abs_tol=1e-9)

    command = SimpleNamespace(
        header=header(2.0, "map"),
        position=point(5.0, 6.0, 1.0),
        velocity=vector(0.3, 0.4, 0.0),
        acceleration=vector(0.1, 0.0, 0.0),
        yaw=0.5,
        yaw_dot=0.1,
        trajectory_id=7,
        trajectory_flag=1,
    )
    planner_event = module.planner_command_event(command, receive_monotonic=31.0, receive_wall_time=41.0)
    assert planner_event["position_local"] == [5.0, 6.0, 1.0]
    assert planner_event["velocity_local"] == [0.3, 0.4, 0.0]
    assert math.isclose(planner_event["velocity_norm_mps"], 0.5, abs_tol=1e-9)
    assert math.isclose(planner_event["acceleration_norm_mps2"], 0.1, abs_tol=1e-9)
    assert planner_event["yaw"] == 0.5
    assert planner_event["trajectory_id"] == 7
    assert planner_event["trajectory_flag"] == 1

    mask = 8 | 16 | 32 | 64 | 128 | 256 | 512 | 2048
    target = SimpleNamespace(
        header=header(2.1, "uav1_odom"),
        coordinate_frame=1,
        type_mask=mask,
        position=point(5.0, 6.0, 1.0),
        velocity=vector(0.3, 0.4, 0.0),
        acceleration_or_force=vector(0.1, 0.0, 0.0),
        yaw=0.5,
        yaw_rate=0.0,
    )
    target_event = module.position_target_event(target, receive_monotonic=32.0, receive_wall_time=42.0)
    assert target_event["coordinate_frame"] == 1
    assert target_event["type_mask"] == mask
    assert target_event["velocity_ignored"] is True
    assert target_event["acceleration_ignored"] is True
    assert target_event["force_enabled"] is True
    assert target_event["position_local"] == [5.0, 6.0, 1.0]
    assert target_event["acceleration_or_force_local"] == [0.1, 0.0, 0.0]

    bspline = SimpleNamespace(
        drone_id=0,
        order=3,
        traj_id=11,
        start_time=SimpleNamespace(secs=3, nsecs=500000000),
        knots=[0.0, 0.1, 0.2, 0.3, 0.4],
        pos_pts=[point(1.0, 2.0, 3.0), point(4.0, 5.0, 6.0)],
        yaw_pts=[0.0, 0.1],
        yaw_dt=0.2,
    )
    bspline_event = module.bspline_event(bspline, receive_monotonic=33.0, receive_wall_time=43.0)
    assert bspline_event["drone_id"] == 0
    assert bspline_event["traj_id"] == 11
    assert bspline_event["knot_count"] == 5
    assert bspline_event["pos_pts"] == [[1.0, 2.0, 3.0], [4.0, 5.0, 6.0]]
    assert math.isclose(bspline_event["start_time_sec"], 3.5, abs_tol=1e-9)

    assert module.validate_cloud_frame("uav1_camera_init", ["uav1_camera_init", "camera_init"]) is True
    assert module.validate_cloud_frame("camera_init", ["uav1_camera_init", "camera_init"]) is True
    assert module.validate_cloud_frame("uav1_map", ["uav1_camera_init", "camera_init"]) is False
    assert module.validate_cloud_frame("", ["uav1_camera_init"]) is False

    source = SCRIPT.read_text(encoding="utf-8")
    assert "rospy.Publisher" not in source
    assert "rospy.ServiceProxy" not in source
    assert "/uav2/planning" not in source
    assert "/uav1/mavros/setpoint_raw/local" in source
    assert "/drone_0_planning/bspline" in source
    print("competition_course_v2_navigation_recorder_check: PASS")


if __name__ == "__main__":
    main()
