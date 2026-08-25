#!/usr/bin/env python3
"""Machine-readable competition metric reference contract."""

import argparse
import json
import math
import sys
import tempfile
from pathlib import Path


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--project-root", default=".")
    args = parser.parse_args()
    root = Path(args.project_root).resolve()
    script_dir = root / "future_aircraft_ws/src/multi_uav_mission/scripts"
    sys.path.insert(0, str(script_dir))
    from competition_course_artifacts import build_evaluation_reference, generate_artifacts
    from competition_course_geometry import (
        build_entity_manifest,
        load_spec,
        pendulum_clearance_report,
        spawn_clearance_report,
        static_clearance_reports,
        turn_clearance_reports,
    )

    spec = load_spec(root / "config/maps/competition_course_v2.json")
    entities = build_entity_manifest(spec)
    reports = {
        "static": static_clearance_reports(spec),
        "turns": turn_clearance_reports(spec),
        "spawn": spawn_clearance_report(spec),
        "pendulum": pendulum_clearance_report(spec),
    }
    reference = build_evaluation_reference(spec, entities, reports)
    assert reference["spec_sha256"] == spec["spec_sha256"]
    assert reference["coordinate_frame"] == "ENU"
    assert reference["ground_truth_transport"] == "NOT_AUDITED_IN_MAP_TASK"
    assert reference["evidence_planes"]["rviz"]["scoring_source"] is False
    assert [item["name"] for item in reference["course_progress"]] == [item["name"] for item in spec["course"]]
    assert reference["course_progress"][0]["s_start_m"] == 0.0
    assert all(item["s_end_m"] > item["s_start_m"] for item in reference["course_progress"])
    expected_total = 4.5 + math.pi * 0.9 / 2 + 3.1 + math.pi * 0.9 / 2 + 4.5
    assert math.isclose(reference["course_progress"][-1]["s_end_m"], expected_total)
    assert reference["geometry"]["wall_polygons"]
    assert len(reference["geometry"]["static_obstacle_polygons"]) == 2
    assert len(reference["geometry"]["landing_polygons"]) == 2
    assert reference["geometry"]["target_truth"]["asset"] == "placeholder"
    assert reference["dynamic_obstacle"]["period_sec"] == 6.0
    assert reference["dynamic_obstacle"]["safe_windows_sec"]
    assert reference["dynamic_obstacle"]["longest_safe_window_sec"] >= 1.5
    assert reference["clearance_policy"] == spec["clearance_policy"]
    expected_metrics = {
        "takeoff_time", "corridor_entry_time", "segment_completion",
        "wall_clearance", "static_obstacle_clearance", "dynamic_obstacle_clearance",
        "inter_uav_distance", "collision_count", "offboard_loss_count",
        "target_error", "landing_error", "localization_error",
    }
    assert {metric["id"] for metric in reference["metrics"]} == expected_metrics
    assert all(metric["primary_evidence"] != "rviz" for metric in reference["metrics"])

    with tempfile.TemporaryDirectory() as temp:
        output = Path(temp)
        generate_artifacts(root / "config/maps/competition_course_v2.json", output)
        saved = json.loads((output / "evaluation_reference.json").read_text(encoding="utf-8"))
        assert saved == reference

    print("competition_course_v2_evaluation_reference_check: PASS")


if __name__ == "__main__":
    main()
