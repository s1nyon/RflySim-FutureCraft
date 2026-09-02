#!/usr/bin/env python3
"""Deterministic ENU-to-RflySim boundary checks for Competition Course V2."""

import argparse
import math
import sys
from pathlib import Path


class FakeApi:
    def __init__(self):
        self.calls = []

    def sendUE4PosScale(self, **kwargs):
        self.calls.append(kwargs)


def close_list(actual, expected):
    assert len(actual) == len(expected)
    assert all(math.isclose(a, e, abs_tol=1e-12) for a, e in zip(actual, expected)), (actual, expected)


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--project-root", default=".")
    args = parser.parse_args()
    root = Path(args.project_root).resolve()
    sys.path.insert(0, str(root / "future_aircraft_ws/src/multi_uav_mission/scripts"))

    from narrow_course_geometry import Vec3, enu_to_ned, yaw_enu_to_ned
    from competition_course_ue_loader import _create_box, rflysim_box_request

    assert enu_to_ned(Vec3(0.0, 0.0, 0.0)) == Vec3(0.0, 0.0, -0.0)
    assert enu_to_ned(Vec3(1.0, 0.0, 0.0)) == Vec3(0.0, 1.0, -0.0)
    assert enu_to_ned(Vec3(0.0, 1.0, 0.0)) == Vec3(1.0, 0.0, -0.0)
    assert enu_to_ned(Vec3(3.0, -2.0, 4.0)) == Vec3(-2.0, 3.0, -4.0)
    assert math.isclose(yaw_enu_to_ned(0.0), math.pi / 2.0)
    assert math.isclose(yaw_enu_to_ned(math.pi / 2.0), 0.0)
    assert math.isclose(yaw_enu_to_ned(-math.pi / 2.0), math.pi)
    assert math.isclose(yaw_enu_to_ned(math.pi), -math.pi / 2.0)

    item = {
        "id": 15042,
        "vehicle_type": 1000813,
        "center": [3.0, -2.0, 4.0],
        "size": [2.0, 3.0, 4.0],
        "scale": [2.0, 3.0, 2.0],
        "yaw_rad": math.pi,
    }
    request = rflysim_box_request(item, window_id=7)
    assert request["copterID"] == 15042
    assert request["vehicleType"] == 1000813
    assert request["windowID"] == 7
    close_list(request["PosE"], [-2.0, 3.0, -4.0])
    close_list(request["AngEuler"], [0.0, 0.0, -math.pi / 2.0])
    close_list(request["Scale"], [2.0, 3.0, 2.0])

    api = FakeApi()
    _create_box(api, item, 7)
    assert api.calls == [request]
    print("competition_course_v2_transform_check: PASS")


if __name__ == "__main__":
    main()
