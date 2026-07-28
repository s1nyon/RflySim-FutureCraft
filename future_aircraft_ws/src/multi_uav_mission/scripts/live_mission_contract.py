#!/usr/bin/env python3
"""Build the Stage 5B live ROS/MAVROS mission boundary plan."""

import argparse
import json
import sys
from pathlib import Path


REQUIRED_STAGES = (
    "MultiTakeoff",
    "EnterCorridor",
    "CollaborativeNavigate",
    "CollaborativeTargetWork",
    "ExitCorridor",
    "ArucoLanding",
    "MissionReport",
)
REQUIRED_UAVS = {
    "uav1": "/uav1",
    "uav2": "/uav2",
}
REQUIRED_LIVE_UAV_FIELDS = (
    "uav_id",
    "namespace",
    "state_topic",
    "odom_topic",
    "setpoint_topic",
    "set_mode_service",
    "arming_service",
    "planner_goal_topic",
)
REQUIRED_STAGE_BINDING_TYPES = {
    "MultiTakeoff": "mavros_offboard_takeoff",
    "EnterCorridor": "fixed_waypoint_setpoint",
    "CollaborativeNavigate": "planner_goal_dispatch",
    "CollaborativeTargetWork": "target_provider_query",
    "ExitCorridor": "fixed_waypoint_setpoint",
    "ArucoLanding": "mavros_auto_land",
    "MissionReport": "score_report",
}


def load_json(path):
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as exc:
        raise ValueError(f"invalid JSON in {path}: {exc.msg}") from exc


def _uav_map(config):
    result = {}
    for index, uav in enumerate(config.get("uavs", [])):
        if not isinstance(uav, dict):
            raise ValueError(f"uavs[{index}] must be an object")
        uav_id = uav.get("uav_id")
        namespace = uav.get("namespace")
        if not uav_id or not namespace:
            raise ValueError(f"uavs[{index}] missing required uav_id or namespace")
        if uav_id in result:
            raise ValueError(f"duplicate UAV id '{uav_id}'")
        result[uav_id] = uav
    return result


def validate_configs(behavior_config, live_config):
    if live_config.get("mission_mode") != "live_ros_boundary":
        raise ValueError("mission_mode must be 'live_ros_boundary'")
    if float(live_config.get("setpoint_rate_hz", 0)) < 20:
        raise ValueError("setpoint_rate_hz must be at least 20")
    if not live_config.get("event_topic"):
        raise ValueError("missing event_topic")
    if not live_config.get("target_provider_service"):
        raise ValueError("missing target_provider_service")

    behavior_uavs = _uav_map(behavior_config)
    live_uavs = _uav_map(live_config)
    if {key: value["namespace"] for key, value in behavior_uavs.items()} != REQUIRED_UAVS:
        raise ValueError("behavior config must define exactly uav1:/uav1 and uav2:/uav2")
    if {key: value["namespace"] for key, value in live_uavs.items()} != REQUIRED_UAVS:
        raise ValueError("live config must define exactly uav1:/uav1 and uav2:/uav2")

    for uav_id, uav in live_uavs.items():
        for field in REQUIRED_LIVE_UAV_FIELDS:
            if not uav.get(field):
                raise ValueError(f"{uav_id} missing required live field '{field}'")

    stage_names = [stage.get("name") for stage in behavior_config.get("stages", [])]
    if tuple(stage_names) != REQUIRED_STAGES:
        raise ValueError("behavior stage sequence must match Stage 5 contract")

    stage_bindings = live_config.get("stage_bindings")
    if not isinstance(stage_bindings, dict):
        raise ValueError("stage_bindings must be an object")
    for stage_name in REQUIRED_STAGES:
        binding = stage_bindings.get(stage_name)
        if not isinstance(binding, dict):
            raise ValueError(f"missing binding for stage '{stage_name}'")
        expected_type = REQUIRED_STAGE_BINDING_TYPES[stage_name]
        if binding.get("type") != expected_type:
            raise ValueError(f"stage '{stage_name}' binding type must be '{expected_type}'")


def _goal_for_stage(stage, uav=None):
    if uav and stage.get("name") == "MultiTakeoff":
        return uav.get("takeoff_goal")
    if uav and stage.get("name") == "ArucoLanding":
        return uav.get("landing_goal")
    return stage.get("goal")


def _sorted_uavs(config):
    return sorted(config["uavs"], key=lambda item: item["uav_id"])


def _stage_lookup(config):
    return {stage["name"]: stage for stage in config["stages"]}


def build_plan(behavior_config, live_config):
    validate_configs(behavior_config, live_config)
    behavior_uavs = _sorted_uavs(behavior_config)
    live_uavs = _sorted_uavs(live_config)
    stages = _stage_lookup(behavior_config)
    bindings = live_config["stage_bindings"]

    actions = []
    sequence = 1

    for live_uav in live_uavs:
        actions.append(
            {
                "sequence": sequence,
                "stage": "preflight",
                "action": "wait_for_topics",
                "uav": live_uav["uav_id"],
                "topics": [live_uav["state_topic"], live_uav["odom_topic"]],
            }
        )
        sequence += 1

    multi_takeoff = stages["MultiTakeoff"]
    takeoff_binding = bindings["MultiTakeoff"]
    for behavior_uav, live_uav in zip(behavior_uavs, live_uavs):
        actions.extend(
            [
                {
                    "sequence": sequence,
                    "stage": "multi_takeoff",
                    "action": "publish_warmup_setpoints",
                    "uav": live_uav["uav_id"],
                    "topic": live_uav["setpoint_topic"],
                    "count": takeoff_binding["pre_setpoint_count"],
                    "rate_hz": live_config["setpoint_rate_hz"],
                    "goal": _goal_for_stage(multi_takeoff, behavior_uav),
                },
                {
                    "sequence": sequence + 1,
                    "stage": "multi_takeoff",
                    "action": "call_service",
                    "uav": live_uav["uav_id"],
                    "service": live_uav["set_mode_service"],
                    "request": {"custom_mode": "OFFBOARD"},
                },
                {
                    "sequence": sequence + 2,
                    "stage": "multi_takeoff",
                    "action": "call_service",
                    "uav": live_uav["uav_id"],
                    "service": live_uav["arming_service"],
                    "request": {"value": True},
                },
                {
                    "sequence": sequence + 3,
                    "stage": "multi_takeoff",
                    "action": "publish_position_setpoint",
                    "uav": live_uav["uav_id"],
                    "topic": live_uav["setpoint_topic"],
                    "rate_hz": live_config["setpoint_rate_hz"],
                    "timeout_s": multi_takeoff["timeout_s"],
                    "goal": _goal_for_stage(multi_takeoff, behavior_uav),
                },
            ]
        )
        sequence += 4

    for stage_name in ("EnterCorridor", "CollaborativeNavigate"):
        stage = stages[stage_name]
        stage_key = _stage_key(stage_name)
        for live_uav in live_uavs:
            if stage_name == "CollaborativeNavigate":
                action = {
                    "sequence": sequence,
                    "stage": stage_key,
                    "action": "publish_planner_goal",
                    "uav": live_uav["uav_id"],
                    "topic": live_uav["planner_goal_topic"],
                    "fallback": bindings[stage_name]["fallback"],
                    "timeout_s": stage["timeout_s"],
                    "goal": stage["goal"],
                }
            else:
                action = {
                    "sequence": sequence,
                    "stage": stage_key,
                    "action": "publish_position_setpoint",
                    "uav": live_uav["uav_id"],
                    "topic": live_uav["setpoint_topic"],
                    "rate_hz": live_config["setpoint_rate_hz"],
                    "timeout_s": stage["timeout_s"],
                    "goal": stage["goal"],
                }
            actions.append(action)
            sequence += 1

    target_stage = stages["CollaborativeTargetWork"]
    actions.append(
        {
            "sequence": sequence,
            "stage": "collaborative_target_work",
            "action": "call_service",
            "service": live_config["target_provider_service"],
            "request": {
                "target_types": [target["target_type"] for target in target_stage.get("targets", [])],
                "timeout_s": target_stage["timeout_s"],
            },
        }
    )
    sequence += 1

    exit_stage = stages["ExitCorridor"]
    for live_uav in live_uavs:
        actions.append(
            {
                "sequence": sequence,
                "stage": "exit_corridor",
                "action": "publish_position_setpoint",
                "uav": live_uav["uav_id"],
                "topic": live_uav["setpoint_topic"],
                "rate_hz": live_config["setpoint_rate_hz"],
                "timeout_s": exit_stage["timeout_s"],
                "goal": exit_stage["goal"],
            }
        )
        sequence += 1

    landing_stage = stages["ArucoLanding"]
    for behavior_uav, live_uav in zip(behavior_uavs, live_uavs):
        actions.append(
            {
                "sequence": sequence,
                "stage": "aruco_landing",
                "action": "call_service",
                "uav": live_uav["uav_id"],
                "service": live_uav["set_mode_service"],
                "request": {"custom_mode": "AUTO.LAND"},
                "timeout_s": landing_stage["timeout_s"],
                "fallback_goal": _goal_for_stage(landing_stage, behavior_uav),
            }
        )
        sequence += 1

    actions.append(
        {
            "sequence": sequence,
            "stage": "mission_report",
            "action": "write_score_report",
            "events_topic": live_config["event_topic"],
            "score_output": live_config["score_output"],
            "timeout_s": stages["MissionReport"]["timeout_s"],
        }
    )

    return {
        "mission_name": behavior_config["mission_name"],
        "mission_mode": live_config["mission_mode"],
        "event_topic": live_config["event_topic"],
        "setpoint_rate_hz": live_config["setpoint_rate_hz"],
        "uavs": [
            {
                "uav_id": live_uav["uav_id"],
                "namespace": live_uav["namespace"],
                "state_topic": live_uav["state_topic"],
                "odom_topic": live_uav["odom_topic"],
                "setpoint_topic": live_uav["setpoint_topic"],
                "planner_goal_topic": live_uav["planner_goal_topic"],
            }
            for live_uav in live_uavs
        ],
        "actions": actions,
    }


def _stage_key(stage_name):
    result = []
    for index, char in enumerate(stage_name):
        if char.isupper() and index > 0:
            result.append("_")
        result.append(char.lower())
    return "".join(result)


def main(argv=None):
    parser = argparse.ArgumentParser(description="Generate Stage 5B live mission boundary plan")
    parser.add_argument("--behavior-config", required=True, type=Path, help="Path to stage5_behavior_tree.json")
    parser.add_argument("--live-config", required=True, type=Path, help="Path to stage5_live_mission.json")
    parser.add_argument("--output", required=True, type=Path, help="Path to write live_mission_plan.json")
    args = parser.parse_args(argv)

    try:
        behavior_config = load_json(args.behavior_config)
        live_config = load_json(args.live_config)
        plan = build_plan(behavior_config, live_config)
        args.output.parent.mkdir(parents=True, exist_ok=True)
        with args.output.open("w", encoding="utf-8", newline="\n") as handle:
            json.dump(plan, handle, indent=2, sort_keys=True)
            handle.write("\n")
    except Exception as exc:
        print(f"[ERROR] {exc}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
