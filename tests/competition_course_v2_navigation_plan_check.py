#!/usr/bin/env python3
"""Behavior contract for isolated Competition Course V2 UAV1 plans."""

from __future__ import annotations

import argparse
import importlib.util
import json
import math
import sys
import tempfile
from pathlib import Path


def load_module(name, path):
    spec = importlib.util.spec_from_file_location(name, str(path))
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def close_xy(actual, expected):
    assert len(actual) == 2
    assert all(math.isclose(float(a), float(e), abs_tol=1e-9) for a, e in zip(actual, expected)), (actual, expected)


def numeric_leaf_paths(value, prefix=""):
    if isinstance(value, dict):
        for key, item in value.items():
            yield from numeric_leaf_paths(item, "{}.{}".format(prefix, key).strip("."))
    elif isinstance(value, list):
        for index, item in enumerate(value):
            yield from numeric_leaf_paths(item, "{}[{}]".format(prefix, index))
    elif isinstance(value, (int, float)) and not isinstance(value, bool):
        yield prefix


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--project-root", default=".")
    args = parser.parse_args()
    root = Path(args.project_root).resolve()
    module_path = root / "future_aircraft_ws/src/multi_uav_mission/scripts/competition_course_navigation_plan.py"
    config_path = root / "config/competition_course_v2_navigation.json"
    assert module_path.is_file(), "V2 navigation plan module is missing"
    assert config_path.is_file(), "V2 navigation config is missing"

    scripts = root / "future_aircraft_ws/src/multi_uav_mission/scripts"
    sys.path.insert(0, str(scripts))
    navigation = load_module("competition_course_navigation_plan", module_path)
    executor = load_module("mission_executor_for_v2_plan", scripts / "mission_executor.py")
    from competition_course_geometry import load_spec

    close_xy(navigation.world_to_local_xy((3.0, 4.0), (1.0, 1.0), 0.0), (2.0, 3.0))
    close_xy(navigation.world_to_local_xy((1.0, 0.0), (0.0, 0.0), 90.0), (0.0, -1.0))
    close_xy(navigation.world_to_local_xy((1.0, 0.0), (0.0, 0.0), -90.0), (0.0, 1.0))
    close_xy(navigation.world_to_local_xy((1.0, 2.0), (0.0, 0.0), 180.0), (-1.0, -2.0))
    close_xy(navigation.world_to_local_xy((23.0, 0.0), (16.0, -0.7), 0.0), (7.0, 0.7))
    for yaw in (0.0, 90.0, -90.0, 180.0, 37.5):
        local = navigation.world_to_local_xy((8.25, -3.5), (4.0, 2.0), yaw)
        close_xy(navigation.local_to_world_xy(local, (4.0, 2.0), yaw), (8.25, -3.5))

    nav_config = json.loads(config_path.read_text(encoding="utf-8"))
    forbidden_geometry_names = ("spawn", "center", "pivot", "start", "end", "position")
    assert not any(
        any(name in path.lower() for name in forbidden_geometry_names)
        for path in numeric_leaf_paths(nav_config)
    ), "navigation config must not contain map geometry coordinates"

    live_config = json.loads((root / "config/stage7_live_slam_ego_swarm.json").read_text(encoding="utf-8"))
    map_spec = load_spec(root / "config/maps/competition_course_v2.json")
    section = next(item for item in map_spec["course"] if item["name"] == "section_a")
    static_box = next(item for item in map_spec["static_obstacles"] if item["name"] == "static_box_a")
    pendulum = map_spec["dynamic_obstacle"]

    short_plan = navigation.build_plan(live_config, map_spec, nav_config, "short_smoke")
    full_plan = navigation.build_plan(live_config, map_spec, nav_config, "full_section_a")
    executor.validate_plan(short_plan)
    executor.validate_plan(full_plan)
    dry_events, dry_trace = executor.execute_plan(
        full_plan, executor.DryRunBackend(), simulation_only=True
    )
    assert dry_events[-1]["event"] == "mission_end"
    assert len(dry_trace) == len(full_plan["actions"])
    takeoff_events = [event for event in dry_events if event["event"] == "takeoff_setpoint_published"]
    assert len(takeoff_events) == 1 and takeoff_events[0]["stage"] == "takeoff"

    for plan in (short_plan, full_plan):
        assert plan["mission_name"].startswith("competition_course_v2_uav1_")
        assert plan["map_contract"]["spec_sha256"] == map_spec["spec_sha256"]
        assert plan["navigation_contract"]["section"] == "section_a"
        assert plan["evaluation_contract"] == {
            "runtime_decision_source": "lidar_driven",
            "evaluation_truth_used": False,
            "truth_must_not_feed_control": True,
        }
        assert {action.get("uav") for action in plan["actions"] if action.get("uav")} == {"uav1"}
        assert not any(action.get("uav") == "uav2" for action in plan["actions"])
        assert [action["stage"] for action in plan["actions"]] == [
            "preflight", "preflight", "takeoff", "takeoff", "takeoff",
            "v2_navigation", "terminal_settle", "landing", "report",
        ]
        publishes = [action for action in plan["actions"] if action["action"] == "publish_planner_goal"]
        verifies = [action for action in plan["actions"] if action["action"] == "verify_planned_navigation"]
        assert len(publishes) == 1 and len(verifies) == 1
        assert publishes[0]["goal"] == verifies[0]["goal"]
        assert "progress_mode" not in verifies[0]
        assert verifies[0]["tolerance_m"] == 0.25
        assert verifies[0]["maximum_speed_mps"] == 0.15
        assert verifies[0]["settle_duration_s"] == 3.0
        landing = next(action for action in plan["actions"] if action["stage"] == "landing")
        assert landing["request"] == {"custom_mode": "AUTO.LAND"}
        assert landing["require_disarmed"] is True
        assert 0.0 < landing["disarm_timeout_s"] <= landing["timeout_s"]

    short_contract = short_plan["navigation_contract"]
    assert math.isclose(short_contract["along_track_goal_m"], 0.75, abs_tol=1e-9)
    short_world = short_contract["terminal_world_enu"]
    assert section["start"][0] < short_world[0] < static_box["center"][0] < pendulum["pivot"][0]
    assert short_contract["obstacle_regions_before_terminal"] == []

    full_contract = full_plan["navigation_contract"]
    close_xy(full_contract["terminal_world_enu"][:2], section["end"])
    close_xy(full_contract["terminal_local"][:2], (7.0, 0.7))
    assert full_contract["expected_obstacle_passage"] == ["static_box_a", "moving_pendulum"]

    with tempfile.TemporaryDirectory() as temp:
        output = Path(temp) / "plan.json"
        exit_code = navigation.main([
            "--config", str(root / "config/stage7_live_slam_ego_swarm.json"),
            "--map-spec", str(root / "config/maps/competition_course_v2.json"),
            "--navigation-config", str(config_path),
            "--profile", "short_smoke",
            "--output", str(output),
        ])
        assert exit_code == 0 and output.is_file()
        assert json.loads(output.read_text(encoding="utf-8"))["navigation_contract"]["profile"] == "short_smoke"

    print("competition_course_v2_navigation_plan_check: PASS")


if __name__ == "__main__":
    main()
