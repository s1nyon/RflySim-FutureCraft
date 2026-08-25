#!/usr/bin/env python3
"""Numerical passability contracts for Competition Course V2."""

import argparse
import copy
import json
import math
import sys
from pathlib import Path


def expect_error(function, needle):
    try:
        function()
    except ValueError as exc:
        assert needle in str(exc), (needle, str(exc))
    else:
        raise AssertionError("expected ValueError containing {!r}".format(needle))


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--project-root", default=".")
    args = parser.parse_args()
    root = Path(args.project_root).resolve()
    sys.path.insert(0, str(root / "future_aircraft_ws/src/multi_uav_mission/scripts"))
    from competition_course_geometry import (
        pendulum_clearance_report,
        spawn_clearance_report,
        static_clearance_reports,
        turn_clearance_reports,
        validate_spec,
    )

    spec = json.loads((root / "config/maps/competition_course_v2.json").read_text(encoding="utf-8"))
    static_reports = static_clearance_reports(spec)
    assert len(static_reports) == 2
    assert all(report["passes"] for report in static_reports)
    assert all(report["passable_gap_m"] >= 1.0 for report in static_reports)

    exact = copy.deepcopy(spec)
    exact["static_obstacles"][0]["size"][1] = 0.20
    exact["static_obstacles"][0]["center"][1] = 0.35
    report = static_clearance_reports(exact)[0]
    assert math.isclose(report["passable_gap_m"], 1.0, abs_tol=1e-12)
    assert report["passes"]
    below = copy.deepcopy(exact)
    below["static_obstacles"][0]["center"][1] = 0.34
    report = static_clearance_reports(below)[0]
    assert math.isclose(report["passable_gap_m"], 0.99, abs_tol=1e-12)
    assert not report["passes"]
    expect_error(lambda: validate_spec(below), "static_box_a")

    turns = turn_clearance_reports(spec)
    assert {item["name"] for item in turns} == {"corner_a", "corner_b"}
    expected_a = (1.5 - 0.45) / 2 - 0.02
    expected_b = (1.4 - 0.45) / 2 - 0.02
    assert math.isclose(next(item for item in turns if item["name"] == "corner_a")["center_margin_m"], expected_a)
    assert math.isclose(next(item for item in turns if item["name"] == "corner_b")["center_margin_m"], expected_b)
    assert all(item["passes"] for item in turns)

    spawn = spawn_clearance_report(spec)
    assert spawn["passes"]
    assert spawn["headings_toward_entry"] == {"uav1": True, "uav2": True}
    outside = copy.deepcopy(spec)
    outside["spawns"]["uav1"][0] = 13.6
    assert not spawn_clearance_report(outside)["passes"]
    expect_error(lambda: validate_spec(outside), "uav1 spawn")
    backwards = copy.deepcopy(spec)
    backwards["spawn_yaw_deg"]["uav2"] = 180.0
    assert not spawn_clearance_report(backwards)["passes"]
    expect_error(lambda: validate_spec(backwards), "uav2 spawn heading")

    pendulum = pendulum_clearance_report(spec)
    assert pendulum["passes"]
    assert pendulum["longest_safe_window_sec"] >= 1.5
    assert pendulum["maximum_open_side_gap_m"] >= 1.0
    fast = copy.deepcopy(spec)
    fast["dynamic_obstacle"]["period_sec"] = 4.0
    assert pendulum_clearance_report(fast)["longest_safe_window_sec"] < 1.5
    expect_error(lambda: validate_spec(fast), "moving_pendulum")

    print("competition_course_v2_clearance_check: PASS")


if __name__ == "__main__":
    main()
