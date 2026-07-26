#!/usr/bin/env python3
"""Generate ego-swarm launch command contracts from Stage 4 config."""

import argparse
import json
import sys
from pathlib import Path


REQUIRED_UAV_FIELDS = (
    "uav_id",
    "namespace",
    "odom_topic",
    "goal_topic",
    "trajectory_topic",
)


def load_config(path):
    try:
        config = json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as exc:
        raise ValueError(f"invalid JSON in {path}: {exc.msg}") from exc

    if config.get("planner") != "ego-swarm":
        raise ValueError("planner must be 'ego-swarm'")
    if not config.get("source_dir"):
        raise ValueError("missing required field 'source_dir'")
    if not isinstance(config.get("uavs"), list) or not config["uavs"]:
        raise ValueError("missing required non-empty list 'uavs'")

    for index, uav in enumerate(config["uavs"], start=1):
        for field in REQUIRED_UAV_FIELDS:
            if not uav.get(field):
                raise ValueError(f"uavs[{index - 1}] missing required field '{field}'")
    return config


def build_commands(config):
    frame_id = config.get("default_frame_id", "map")
    uav_commands = []

    for index, uav in enumerate(config["uavs"], start=1):
        uav_frame = uav.get("frame_id", frame_id)
        launch_command = (
            "roslaunch ego_planner swarm.launch "
            f"drone_id:={index} "
            f"odom_topic:={uav['odom_topic']} "
            f"goal_topic:={uav['goal_topic']} "
            f"trajectory_topic:={uav['trajectory_topic']} "
            f"frame_id:={uav_frame}"
        )
        uav_commands.append(
            {
                "uav_id": uav["uav_id"],
                "namespace": uav["namespace"],
                "odom_topic": uav["odom_topic"],
                "goal_topic": uav["goal_topic"],
                "trajectory_topic": uav["trajectory_topic"],
                "frame_id": uav_frame,
                "launch_command": launch_command,
            }
        )

    return {
        "planner": config["planner"],
        "source_dir": config["source_dir"],
        "fallback_mode": config.get("fallback_mode", "fixed_waypoint"),
        "uavs": uav_commands,
    }


def main(argv=None):
    parser = argparse.ArgumentParser(description="Generate ego-swarm adapter command summary")
    parser.add_argument("--config", required=True, type=Path, help="Path to stage4_ego_swarm.json")
    parser.add_argument("--output", required=True, type=Path, help="Path to write generated command JSON")
    args = parser.parse_args(argv)

    try:
        config = load_config(args.config)
        command_summary = build_commands(config)
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(json.dumps(command_summary, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    except Exception as exc:
        print(f"[ERROR] {exc}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
