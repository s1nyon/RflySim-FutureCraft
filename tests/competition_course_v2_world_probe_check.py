#!/usr/bin/env python3
"""Offline contract checks for the run-scoped V2 world-state retention probe."""

from __future__ import annotations

import argparse
import json
import math
import subprocess
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

    from competition_course_world_probe import (
        build_probe_report,
        entity_errors,
        evaluate_dynamic,
        verify_receipt_scope,
    )
    from competition_course_geometry import load_spec

    spec = load_spec(root / "config/maps/competition_course_v2.json")
    wall = {
        "id": 15000, "name": "section_a_left", "category": "wall",
        "center": [20.75, 0.825, 0.0], "size": [4.5, 0.15, 2.5],
        "yaw_rad": 0.0,
    }
    correct = {
        "position_ned_m": [0.825, 20.75, 0.0],
        "attitude_vendor_rad": [0.0, 0.0, math.pi / 2.0],
        "asset_local_dimensions_m": [4.5, 0.15, 2.5],
    }
    assert entity_errors(wall, correct) == []

    wrong_position = dict(correct)
    wrong_position["position_ned_m"] = [0.875, 20.75, 0.0]
    assert entity_errors(wall, wrong_position)[0]["kind"] == "position"

    wrong_dimension = dict(correct)
    wrong_dimension["asset_local_dimensions_m"] = [1.5, 0.15, 2.5]
    assert entity_errors(wall, wrong_dimension)[0]["kind"] == "dimension"

    wrong_yaw = dict(correct)
    wrong_yaw["attitude_vendor_rad"] = [0.0, 0.0, 0.0]
    assert entity_errors(wall, wrong_yaw)[0]["kind"] == "yaw"

    dynamic_item = {
        "id": 15120, "name": "moving_pendulum", "category": "dynamic_obstacle",
        "center": list(spec["dynamic_obstacle"]["pivot"]), "size": [0.25, 0.2, 0.7],
    }
    moving = [
        {"position_enu_m": [22.0, 0.0, 1.2], "asset_local_dimensions_m": [0.25, 0.2, 0.7]},
        {"position_enu_m": [22.0, 0.3, 1.24], "asset_local_dimensions_m": [0.25, 0.2, 0.7]},
        {"position_enu_m": [22.0, 0.6, 1.36], "asset_local_dimensions_m": [0.25, 0.2, 0.7]},
    ]
    dynamic_pass = evaluate_dynamic(dynamic_item, moving)
    assert dynamic_pass["motion_errors"] == []

    native_size = [dict(sample) for sample in moving]
    native_size[-1]["asset_local_dimensions_m"] = [0.25, 0.2, 2.1]
    assert evaluate_dynamic(dynamic_item, native_size)["motion_errors"][0]["kind"] == "dimension"

    frozen = [
        {"position_enu_m": [22.0, 0.0, 1.2], "asset_local_dimensions_m": [0.25, 0.2, 0.7]},
        {"position_enu_m": [22.0, 0.01, 1.2], "asset_local_dimensions_m": [0.25, 0.2, 0.7]},
    ]
    assert evaluate_dynamic(dynamic_item, frozen)["motion_errors"][0]["kind"] == "motion"

    entities = [wall, dynamic_item]
    observations = {
        "15000": {"name": "section_a_left", "category": "wall", **correct},
        "15120": {"name": "moving_pendulum", "category": "dynamic_obstacle", **moving[-1]},
    }
    clean = build_probe_report(
        "A", "stack-1", "sim-1", spec["spec_sha256"], entities, observations,
        missing_ids=[], errors_by_id={}, dynamic=dynamic_pass,
    )
    assert clean["result"] == "PASS"

    failing = build_probe_report(
        "A", "stack-1", "sim-1", spec["spec_sha256"], entities, {},
        missing_ids=[15000], errors_by_id={}, dynamic=dynamic_pass,
    )
    assert failing["result"] == "FAIL"
    assert failing["missing_ids"] == [15000]

    erroring = build_probe_report(
        "A", "stack-1", "sim-1", spec["spec_sha256"], entities, observations,
        missing_ids=[], errors_by_id={15000: entity_errors(wall, wrong_position)}, dynamic=dynamic_pass,
    )
    assert erroring["result"] == "FAIL"
    assert erroring["errors"][0]["kind"] == "position"

    with tempfile.TemporaryDirectory() as temp:
        receipt = Path(temp) / "load_receipt.json"
        receipt.write_text(json.dumps({
            "map_id": "competition_course_v2", "spec_sha256": spec["spec_sha256"],
            "cleanup_policy": "receipt_only", "stack_id": "stack-old",
            "simulation_instance_id": "sim-old", "created_ids": [],
        }), encoding="utf-8")
        try:
            verify_receipt_scope(receipt, spec["spec_sha256"], "stack-1", "sim-1")
        except ValueError as exc:
            assert "cross-instance" in str(exc)
        else:
            raise AssertionError("cross-instance receipt must be rejected")
        verify_receipt_scope(receipt, spec["spec_sha256"], "stack-old", "sim-old")

    with tempfile.TemporaryDirectory() as temp:
        from competition_course_artifacts import generate_artifacts
        generated = Path(temp) / "generated"
        generate_artifacts(root / "config/maps/competition_course_v2.json", generated)
        dry = subprocess.run(
            [
                sys.executable,
                str(script_dir / "competition_course_world_probe.py"),
                "--spec", str(root / "config/maps/competition_course_v2.json"),
                "--generated", str(generated),
                "--receipt", "unused.json",
                "--stack-id", "stack-1",
                "--simulation-instance-id", "sim-1",
                "--probe-id", "A",
                "--output", "unused_out.json",
                "--dry-run",
            ],
            capture_output=True, text=True,
        )
        assert dry.returncode == 0, dry.stdout + dry.stderr
        plan = json.loads(dry.stdout)
        assert len(plan["requested_ids"]) == 40

    source = (script_dir / "competition_course_world_probe.py").read_text(encoding="utf-8")
    for forbidden in ("sendUE4Destroy", "sendUE4PosScale", "sendUE4PosNew", "sendUE4ExtAct", "rospy", "arming", "set_mode"):
        assert forbidden not in source, forbidden
    print("competition_course_v2_world_probe_check: PASS")


if __name__ == "__main__":
    main()
