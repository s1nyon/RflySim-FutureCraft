#!/usr/bin/env python3
"""Provenance and safety contract for V2 Section A navigation reports."""

from __future__ import annotations

import argparse
import copy
import importlib.util
import json
import sys
from pathlib import Path


def load_module(name, path):
    spec = importlib.util.spec_from_file_location(name, str(path))
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def mission_events():
    names = (
        "offboard_confirmed",
        "arming_confirmed",
        "takeoff_altitude_confirmed",
        "navigation_confirmed",
        "terminal_settle_confirmed",
        "landing_confirmed",
        "disarm_confirmed",
    )
    events = [{"time": index, "event": name, "uav": "uav1"} for index, name in enumerate(names)]
    events.extend([
        {"time": 2.5, "event": "executor_action_success", "action": "publish_planner_goal", "uav": "uav1"},
        {"time": 3.0, "event": "min_uav_distance", "distance_m": 0.85},
    ])
    return events


def recorder_events():
    result = []
    for index, local_x in enumerate((2.5, 4.5, 6.0, 7.0)):
        result.append({
            "kind": "uav1_odom",
            "receive_monotonic": 10.0 + index,
            "position_local": [local_x, 0.7, 1.0],
            "speed_mps": 0.3 if index < 3 else 0.05,
        })
    for index in range(8):
        result.append({
            "kind": "uav2_state_sample",
            "receive_monotonic": 10.0 + index * 0.5,
            "receive_wall_time": 100.0 + index * 0.5,
            "armed": False,
            "mode": "MANUAL",
            "connected": True,
        })
    for index in range(12):
        result.append({"kind": "planner_command", "receive_monotonic": 11.0 + index * 0.1})
    result.extend([
        {
            "kind": "registered_cloud_roi",
            "receive_monotonic": 12.0,
            "regions": {
                "static_box_a": {"point_count": 32, "centroid_local": [4.5, 1.2, 0.5]},
                "moving_pendulum": {"point_count": 20, "centroid_local": [6.0, 0.2, 1.2]},
            },
        },
        {
            "kind": "registered_cloud_roi",
            "receive_monotonic": 13.0,
            "regions": {
                "static_box_a": {"point_count": 35, "centroid_local": [4.5, 1.2, 0.5]},
                "moving_pendulum": {"point_count": 28, "centroid_local": [6.0, 0.55, 1.2]},
            },
        },
    ])
    return result


def monitor_status(available=True):
    return {
        "available": available,
        "source": "rflysim_reqVeCrashData_udp_20006",
        "monitor_started_wall_time": 99.0,
        "last_heartbeat_wall_time": 104.0 if available else 100.0,
        "active_start_wall_time": 100.5,
        "active_end_wall_time": 103.0,
    }


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--project-root", default=".")
    args = parser.parse_args()
    root = Path(args.project_root).resolve()
    scripts = root / "future_aircraft_ws/src/multi_uav_mission/scripts"
    report_path = scripts / "competition_course_navigation_report.py"
    assert report_path.is_file(), "V2 navigation report module is missing"
    sys.path.insert(0, str(scripts))
    report_module = load_module("competition_course_navigation_report", report_path)
    navigation = load_module("competition_course_navigation_plan_for_report", scripts / "competition_course_navigation_plan.py")
    from competition_course_geometry import load_spec

    spec = load_spec(root / "config/maps/competition_course_v2.json")
    live = json.loads((root / "config/stage7_live_slam_ego_swarm.json").read_text(encoding="utf-8"))
    nav = json.loads((root / "config/competition_course_v2_navigation.json").read_text(encoding="utf-8"))
    plan = navigation.build_plan(live, spec, nav, "full_section_a")

    accepted = report_module.build_report(
        plan=plan,
        spec=spec,
        mission_events=mission_events(),
        recorder_events=recorder_events(),
        flight_events=[],
        watchdog_events=[],
        collision_monitor=monitor_status(),
        executor_exit_code=0,
    )
    assert accepted["ready"] is True, accepted
    assert accepted["result"] == "PASS"
    assert accepted["runtime_decision_source"] == "lidar_driven"
    assert accepted["evaluation_truth_used"] is True
    assert "min_uav_distance_m" not in accepted
    assert accepted["uav2_monitor"]["sample_count"] == 8
    assert accepted["uav2_monitor"]["monitoring_interval_s"] == 0.5
    assert accepted["uav2_monitor"]["first_state"]["armed"] is False
    assert accepted["uav2_monitor"]["final_state"]["mode"] == "MANUAL"
    assert accepted["uav2_monitor"]["violations"] == []
    assert accepted["uav2_monitor"]["covered_active_interval"] is True
    assert accepted["progress"]["regions_passed"] == ["static_box_a", "moving_pendulum"]
    assert accepted["progress"]["endpoint_reached"] is True
    assert accepted["perception"]["static_obstacle_observed"] is True
    assert accepted["perception"]["dynamic_temporal_change_observed"] is True
    assert accepted["planner_command_count"] == 12
    assert accepted["collision_count"] == {
        "value": 0,
        "source_class": "simulator_evaluation",
        "source": "rflysim_reqVeCrashData_udp_20006",
    }
    assert accepted["minimum_wall_clearance_m"]["source_class"] == "derived"
    assert accepted["minimum_wall_clearance_m"]["value"] > 0.0
    assert accepted["minimum_static_obstacle_clearance_m"]["source_class"] == "derived"
    assert accepted["minimum_static_obstacle_clearance_m"]["value"] > 0.0
    assert accepted["dynamic_clearance_m"] == {
        "value": None,
        "source_class": "unavailable",
        "source": "no_time_synchronized_dynamic_entity_pose",
    }

    unavailable = report_module.build_report(
        plan=plan,
        spec=spec,
        mission_events=mission_events(),
        recorder_events=recorder_events(),
        flight_events=[],
        watchdog_events=[],
        collision_monitor=monitor_status(False),
        executor_exit_code=0,
    )
    assert unavailable["ready"] is False
    assert unavailable["result"] == "NAVIGATION_SUCCESS_COLLISION_EVIDENCE_INCOMPLETE"
    assert unavailable["collision_count"]["value"] is None
    assert unavailable["collision_count"]["source_class"] == "unavailable"

    late_uav2 = recorder_events()
    late_uav2[:] = [
        item for item in late_uav2
        if item.get("kind") != "uav2_state_sample" or item["receive_wall_time"] >= 101.0
    ]
    uncovered = report_module.build_report(
        plan=plan,
        spec=spec,
        mission_events=mission_events(),
        recorder_events=late_uav2,
        flight_events=[],
        watchdog_events=[],
        collision_monitor=monitor_status(),
        executor_exit_code=0,
    )
    assert uncovered["uav2_monitor"]["covered_active_interval"] is False
    assert "uav2_isolation" in uncovered["failure_reasons"]

    collision = report_module.build_report(
        plan=plan,
        spec=spec,
        mission_events=mission_events(),
        recorder_events=recorder_events(),
        flight_events=[{"event": "collision", "copter_id": 1, "crash_type": 2, "timestamp": 102.0}],
        watchdog_events=[],
        collision_monitor=monitor_status(),
        executor_exit_code=0,
    )
    assert collision["ready"] is False
    assert collision["collision_count"]["value"] == 1
    assert "collision" in collision["failure_reasons"]

    preflight_collision = report_module.build_report(
        plan=plan,
        spec=spec,
        mission_events=mission_events(),
        recorder_events=recorder_events(),
        flight_events=[{"event": "collision", "copter_id": 1, "timestamp": 99.5}],
        watchdog_events=[],
        collision_monitor=monitor_status(),
        executor_exit_code=0,
    )
    assert preflight_collision["collision_count"]["value"] == 0
    assert preflight_collision["collision_count"]["ignored_outside_active_interval"] == 1

    expected_land_transition = report_module.build_report(
        plan=plan,
        spec=spec,
        mission_events=mission_events(),
        recorder_events=recorder_events(),
        flight_events=[{"event": "mode_loss", "uav": "uav1", "mode": "AUTO.LAND"}],
        watchdog_events=[],
        collision_monitor=monitor_status(),
        executor_exit_code=0,
    )
    assert expected_land_transition["unexpected_offboard_loss"] is False

    expected_land_watchdog = report_module.build_report(
        plan=plan,
        spec=spec,
        mission_events=mission_events(),
        recorder_events=recorder_events(),
        flight_events=[{"event": "mode_loss", "uav": "uav1", "mode": "AUTO.LAND"}],
        watchdog_events=[{"decision": "land", "reason": "mode_loss", "mode": "AUTO.LAND"}],
        collision_monitor=monitor_status(),
        executor_exit_code=0,
    )
    assert expected_land_watchdog["watchdog_or_geofence_trip"] is False

    unexpected_mode_loss = report_module.build_report(
        plan=plan,
        spec=spec,
        mission_events=mission_events(),
        recorder_events=recorder_events(),
        flight_events=[{"event": "mode_loss", "uav": "uav1", "mode": "POSCTL"}],
        watchdog_events=[],
        collision_monitor=monitor_status(),
        executor_exit_code=0,
    )
    assert unexpected_mode_loss["unexpected_offboard_loss"] is True
    assert "offboard_loss" in unexpected_mode_loss["failure_reasons"]

    uav2_violation_events = recorder_events()
    state = next(item for item in uav2_violation_events if item["kind"] == "uav2_state_sample")
    state["armed"] = True
    state["mode"] = "OFFBOARD"
    isolated = report_module.build_report(
        plan=plan,
        spec=spec,
        mission_events=mission_events(),
        recorder_events=uav2_violation_events,
        flight_events=[],
        watchdog_events=[],
        collision_monitor=monitor_status(),
        executor_exit_code=0,
    )
    assert isolated["ready"] is False
    assert len(isolated["uav2_monitor"]["violations"]) == 1
    assert "uav2_isolation" in isolated["failure_reasons"]

    transient_events = recorder_events()
    transient_events.append({
        "kind": "uav2_state_observation",
        "receive_monotonic": 11.25,
        "receive_wall_time": 101.25,
        "armed": False,
        "mode": "OFFBOARD",
        "connected": True,
    })
    transient = report_module.build_report(
        plan=plan,
        spec=spec,
        mission_events=mission_events(),
        recorder_events=transient_events,
        flight_events=[],
        watchdog_events=[],
        collision_monitor=monitor_status(),
        executor_exit_code=0,
    )
    assert "uav2_isolation" in transient["failure_reasons"]

    disconnected_events = recorder_events()
    next(item for item in disconnected_events if item["kind"] == "uav2_state_sample")["connected"] = False
    disconnected = report_module.build_report(
        plan=plan,
        spec=spec,
        mission_events=mission_events(),
        recorder_events=disconnected_events,
        flight_events=[],
        watchdog_events=[],
        collision_monitor=monitor_status(),
        executor_exit_code=0,
    )
    assert "uav2_isolation" in disconnected["failure_reasons"]

    wall_contact_events = copy.deepcopy(recorder_events())
    first_odom = next(item for item in wall_contact_events if item["kind"] == "uav1_odom")
    first_odom["position_local"] = [2.5, 0.0, 1.0]
    clearance = report_module.build_report(
        plan=plan,
        spec=spec,
        mission_events=mission_events(),
        recorder_events=wall_contact_events,
        flight_events=[],
        watchdog_events=[],
        collision_monitor=monitor_status(),
        executor_exit_code=0,
    )
    assert clearance["minimum_wall_clearance_m"]["value"] < 0.0
    assert clearance["ready"] is False
    assert "wall_clearance" in clearance["failure_reasons"]

    print("competition_course_v2_navigation_report_check: PASS")


if __name__ == "__main__":
    main()
