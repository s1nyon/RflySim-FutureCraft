#!/usr/bin/env python3
"""Serve or write deterministic Stage 6A target results."""

import argparse
import json
import sys
from pathlib import Path


REQUIRED_TARGET_FIELDS = ("target_id", "target_type", "position", "confidence", "uav")
REQUIRED_POSITION_FIELDS = ("x", "y", "z")


def load_config(path):
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as exc:
        raise ValueError(f"invalid JSON in {path}: {exc.msg}") from exc


def parse_target_types(value):
    if value is None or value.strip() == "":
        return []
    return [item.strip() for item in value.split(",") if item.strip()]


def validate_config(config):
    if not isinstance(config, dict):
        raise ValueError("target config must be an object")
    if config.get("source_mode") != "ideal":
        raise ValueError("source_mode must be 'ideal'")
    if not config.get("frame_id"):
        raise ValueError("target config missing frame_id")
    targets = config.get("targets")
    if not isinstance(targets, list) or not targets:
        raise ValueError("targets must be a non-empty list")

    seen_ids = set()
    for index, target in enumerate(targets):
        if not isinstance(target, dict):
            raise ValueError(f"targets[{index}] must be an object")
        for field in REQUIRED_TARGET_FIELDS:
            if field not in target or target[field] in ("", None):
                raise ValueError(f"targets[{index}] missing required field '{field}'")
        target_id = target["target_id"]
        if target_id in seen_ids:
            raise ValueError(f"duplicate target_id '{target_id}'")
        seen_ids.add(target_id)

        confidence = float(target["confidence"])
        if confidence < 0.0 or confidence > 1.0:
            raise ValueError(f"targets[{index}] confidence must be between 0 and 1")

        position = target["position"]
        if not isinstance(position, dict):
            raise ValueError(f"targets[{index}] position must be an object")
        for axis in REQUIRED_POSITION_FIELDS:
            if axis not in position:
                raise ValueError(f"targets[{index}] position missing '{axis}'")
            float(position[axis])


def build_results(config, target_types=None):
    validate_config(config)
    requested_types = list(target_types or [])
    targets = config["targets"]
    if requested_types:
        configured_types = {target["target_type"] for target in targets}
        missing_types = [target_type for target_type in requested_types if target_type not in configured_types]
        if missing_types:
            raise ValueError(f"requested target types are not configured: {', '.join(missing_types)}")
        targets = [target for target in targets if target["target_type"] in requested_types]

    return {
        "source_mode": config["source_mode"],
        "frame_id": config["frame_id"],
        "targets": [
            {
                "target_id": target["target_id"],
                "target_type": target["target_type"],
                "uav": target["uav"],
                "confidence": float(target["confidence"]),
                "position": {
                    "x": float(target["position"]["x"]),
                    "y": float(target["position"]["y"]),
                    "z": float(target["position"]["z"]),
                },
            }
            for target in targets
        ],
    }


def write_json(path, value):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value, indent=2, sort_keys=True) + "\n", encoding="utf-8")


def serve_ros(results, service_name):
    try:
        import rospy
        from std_srvs.srv import Trigger, TriggerResponse
    except ImportError as exc:
        raise RuntimeError(f"ROS backend requires rospy and std_srvs Python packages: {exc}") from exc

    if not rospy.core.is_initialized():
        rospy.init_node("future_aircraft_target_provider", anonymous=True)

    payload = json.dumps(results, sort_keys=True, separators=(",", ":"))

    def handle_trigger(_request):
        return TriggerResponse(success=True, message=payload)

    rospy.Service(service_name, Trigger, handle_trigger)
    rospy.loginfo("future_aircraft target provider serving %s", service_name)
    rospy.spin()


def main(argv=None):
    parser = argparse.ArgumentParser(description="Generate or serve Stage 6A target results")
    parser.add_argument("--config", required=True, type=Path, help="Path to stage6_targets.json")
    parser.add_argument("--target-types", help="Comma-separated target types to include")
    parser.add_argument("--backend", choices=("dry-run", "ros"), default="dry-run", help="Provider backend")
    parser.add_argument("--service", default="/mission/target_provider/query", help="ROS Trigger service name")
    parser.add_argument("--output", type=Path, help="Path to write target_results.json in dry-run mode")
    args = parser.parse_args(argv)

    try:
        config = load_config(args.config)
        results = build_results(config, parse_target_types(args.target_types))
        if args.backend == "ros":
            serve_ros(results, args.service)
        else:
            if args.output is None:
                raise ValueError("--output is required in dry-run mode")
            write_json(args.output, results)
    except Exception as exc:
        print(f"[ERROR] {exc}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
