#!/usr/bin/env python3
"""Generate deterministic Stage 5 behavior-tree contract events."""

import argparse
import json
import re
import sys
from pathlib import Path


SUPPORTED_MODE = "fixed_waypoint_fallback"
SUPPORTED_FAILURE_POLICY = "abort_and_land"
SUPPORTED_UAVS = {
    "uav1": "/uav1",
    "uav2": "/uav2",
}
REQUIRED_STAGE_SEQUENCE = (
    "MultiTakeoff",
    "EnterCorridor",
    "CollaborativeNavigate",
    "CollaborativeTargetWork",
    "ExitCorridor",
    "ArucoLanding",
    "MissionReport",
)


def stage_key(stage_name):
    return re.sub(r"(?<!^)(?=[A-Z])", "_", stage_name).lower()


def load_config(path):
    try:
        config = json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as exc:
        raise ValueError(f"invalid JSON in {path}: {exc.msg}") from exc
    validate_config(config)
    return config


def validate_config(config):
    for field in ("mission_name", "mode", "uavs", "stages", "failure_policy", "event_output_contract"):
        if field not in config:
            raise ValueError(f"missing required field '{field}'")

    if config["mode"] != SUPPORTED_MODE:
        raise ValueError(f"unsupported mode '{config['mode']}'")
    if config["failure_policy"] != SUPPORTED_FAILURE_POLICY:
        raise ValueError(f"unsupported failure_policy '{config['failure_policy']}'")

    uavs = config["uavs"]
    if not isinstance(uavs, list) or len(uavs) != len(SUPPORTED_UAVS):
        raise ValueError("uavs must contain exactly uav1 and uav2")

    observed_uavs = {}
    for index, uav in enumerate(uavs):
        if not isinstance(uav, dict):
            raise ValueError(f"uavs[{index}] must be an object")
        uav_id = uav.get("uav_id")
        namespace = uav.get("namespace")
        if not uav_id or not namespace:
            raise ValueError(f"uavs[{index}] missing required uav_id or namespace")
        if uav_id in observed_uavs:
            raise ValueError(f"duplicate UAV id '{uav_id}'")
        observed_uavs[uav_id] = namespace

    if observed_uavs != SUPPORTED_UAVS:
        raise ValueError("uavs must be exactly uav1:/uav1 and uav2:/uav2")

    stages = config["stages"]
    if not isinstance(stages, list):
        raise ValueError("stages must be a list")
    stage_names = []
    for index, stage in enumerate(stages):
        if not isinstance(stage, dict):
            raise ValueError(f"stages[{index}] must be an object")
        name = stage.get("name")
        if name not in REQUIRED_STAGE_SEQUENCE:
            raise ValueError(f"unknown stage '{name}'")
        if name in stage_names:
            raise ValueError(f"duplicate stage '{name}'")
        if not isinstance(stage.get("timeout_s"), (int, float)) or float(stage["timeout_s"]) <= 0:
            raise ValueError(f"stage '{name}' has invalid timeout_s")
        if not stage.get("success_event"):
            raise ValueError(f"stage '{name}' missing success_event")
        stage_names.append(name)

    if tuple(stage_names) != REQUIRED_STAGE_SEQUENCE:
        raise ValueError("stage sequence must match the Stage 5 contract")

    required_fields = config["event_output_contract"].get("required_fields")
    if required_fields != ["time", "event"]:
        raise ValueError("event_output_contract.required_fields must be ['time', 'event']")


def build_events(config):
    stage_by_name = {stage["name"]: stage for stage in config["stages"]}

    events = [
        {"time": 0.0, "event": "mission_start", "mission": config["mission_name"], "mode": config["mode"]},
        {"time": 0.0, "event": "multi_takeoff_start", "stage": "multi_takeoff"},
        {"time": 4.0, "event": "uav_stage_success", "stage": "multi_takeoff", "uav": "uav1"},
        {"time": 6.0, "event": "uav_stage_success", "stage": "multi_takeoff", "uav": "uav2"},
        {"time": 8.0, "event": stage_by_name["MultiTakeoff"]["success_event"], "stage": "multi_takeoff"},
        {"time": 9.0, "event": "enter_corridor_start", "stage": "enter_corridor"},
        {"time": 16.0, "event": stage_by_name["EnterCorridor"]["success_event"], "stage": "enter_corridor"},
        {"time": 17.0, "event": "collaborative_navigate_start", "stage": "collaborative_navigate"},
        {"time": 24.0, "event": "min_uav_distance", "stage": "collaborative_navigate", "distance_m": 0.85},
        {"time": 30.0, "event": stage_by_name["CollaborativeNavigate"]["success_event"], "stage": "collaborative_navigate"},
        {"time": 31.0, "event": "collaborative_target_work_start", "stage": "collaborative_target_work"},
    ]

    target_stage = stage_by_name["CollaborativeTargetWork"]
    for time_value, target in zip((35.0, 37.0, 39.0), target_stage.get("targets", [])):
        events.append(
            {
                "time": time_value,
                "event": "target_detected",
                "stage": "collaborative_target_work",
                "target_id": target["target_id"],
                "target_type": target["target_type"],
                "uav": target["uav"],
            }
        )

    events.extend(
        [
            {"time": 40.0, "event": target_stage["success_event"], "stage": "collaborative_target_work"},
            {"time": 41.0, "event": "exit_corridor_start", "stage": "exit_corridor"},
            {"time": 45.0, "event": stage_by_name["ExitCorridor"]["success_event"], "stage": "exit_corridor"},
            {"time": 46.0, "event": "aruco_landing_start", "stage": "aruco_landing"},
            {"time": 48.0, "event": "uav_stage_success", "stage": "aruco_landing", "uav": "uav1"},
            {"time": 50.0, "event": "uav_stage_success", "stage": "aruco_landing", "uav": "uav2"},
            {"time": 51.0, "event": stage_by_name["ArucoLanding"]["success_event"], "stage": "aruco_landing"},
            {"time": 51.5, "event": "mission_report_start", "stage": "mission_report"},
            {"time": 51.8, "event": stage_by_name["MissionReport"]["success_event"], "stage": "mission_report"},
            {"time": 52.0, "event": "mission_end", "mission": config["mission_name"]},
        ]
    )
    return events


def main(argv=None):
    parser = argparse.ArgumentParser(description="Generate Stage 5 behavior-tree mission_events.jsonl")
    parser.add_argument("--config", required=True, type=Path, help="Path to stage5_behavior_tree.json")
    parser.add_argument("--output", required=True, type=Path, help="Path to write mission_events.jsonl")
    args = parser.parse_args(argv)

    try:
        config = load_config(args.config)
        events = build_events(config)
        args.output.parent.mkdir(parents=True, exist_ok=True)
        lines = [json.dumps(event, sort_keys=True, separators=(",", ":")) for event in events]
        with args.output.open("w", encoding="utf-8", newline="\n") as handle:
            handle.write("\n".join(lines) + "\n")
    except Exception as exc:
        print(f"[ERROR] {exc}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
