#!/usr/bin/env python3
"""Serve or write deterministic Stage 6B simulation-vision target results."""

import argparse
import json
import sys
from pathlib import Path


REQUIRED_DETECTION_FIELDS = (
    "detection_id",
    "target_id",
    "target_type",
    "uav",
    "camera",
    "confidence",
    "position",
)
REQUIRED_POSITION_FIELDS = ("x", "y", "z")
SUPPORTED_UAVS = ("uav1", "uav2")


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
        raise ValueError("simulation vision config must be an object")
    if config.get("source_mode") != "sim_vision":
        raise ValueError("source_mode must be 'sim_vision'")
    if not config.get("frame_id"):
        raise ValueError("simulation vision config missing frame_id")
    if "default_min_confidence" in config:
        _validate_confidence(config["default_min_confidence"], "default_min_confidence")

    detections = config.get("detections")
    if not isinstance(detections, list) or not detections:
        raise ValueError("detections must be a non-empty list")

    seen_detection_ids = set()
    for index, detection in enumerate(detections):
        if not isinstance(detection, dict):
            raise ValueError(f"detections[{index}] must be an object")
        for field in REQUIRED_DETECTION_FIELDS:
            if field not in detection or detection[field] in ("", None):
                raise ValueError(f"detections[{index}] missing required field '{field}'")

        detection_id = str(detection["detection_id"])
        if detection_id in seen_detection_ids:
            raise ValueError(f"duplicate detection_id '{detection_id}'")
        seen_detection_ids.add(detection_id)

        uav = str(detection["uav"])
        if uav not in SUPPORTED_UAVS:
            raise ValueError(f"detections[{index}] uav must be one of {', '.join(SUPPORTED_UAVS)}")
        _validate_confidence(detection["confidence"], f"detections[{index}] confidence")
        _normalize_position(detection["position"], f"detections[{index}] position")


def build_results(config, target_types=None, min_confidence=None):
    validate_config(config)
    requested_types = list(target_types or [])
    detections = config["detections"]
    configured_types = {detection["target_type"] for detection in detections}
    missing_types = [target_type for target_type in requested_types if target_type not in configured_types]
    if missing_types:
        raise ValueError(f"requested target types are not configured: {', '.join(missing_types)}")

    threshold = _resolve_min_confidence(config, min_confidence)
    selected = []
    seen_target_ids = set()
    for detection in detections:
        if requested_types and detection["target_type"] not in requested_types:
            continue
        if float(detection["confidence"]) < threshold:
            continue
        target_id = str(detection["target_id"])
        if target_id in seen_target_ids:
            raise ValueError(f"duplicate target_id '{target_id}' after filtering")
        seen_target_ids.add(target_id)
        selected.append(detection)

    if not selected:
        raise ValueError("no detections passed target type and confidence filters")

    return {
        "source_mode": config["source_mode"],
        "frame_id": str(config["frame_id"]),
        "targets": [_normalize_detection(detection) for detection in selected],
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
        rospy.init_node("future_aircraft_sim_vision_target_provider", anonymous=True)

    payload = json.dumps(results, sort_keys=True, separators=(",", ":"))

    def handle_trigger(_request):
        return TriggerResponse(success=True, message=payload)

    rospy.Service(service_name, Trigger, handle_trigger)
    rospy.loginfo("future_aircraft sim vision target provider serving %s", service_name)
    rospy.spin()


def _resolve_min_confidence(config, min_confidence):
    value = config.get("default_min_confidence", 0.0) if min_confidence is None else min_confidence
    return _validate_confidence(value, "min_confidence")


def _validate_confidence(value, context):
    confidence = float(value)
    if confidence < 0.0 or confidence > 1.0:
        raise ValueError(f"{context} must be between 0 and 1")
    return confidence


def _normalize_position(position, context):
    if not isinstance(position, dict):
        raise ValueError(f"{context} must be an object")
    normalized = {}
    for axis in REQUIRED_POSITION_FIELDS:
        if axis not in position:
            raise ValueError(f"{context} missing '{axis}'")
        normalized[axis] = float(position[axis])
    return normalized


def _normalize_detection(detection):
    return {
        "target_id": str(detection["target_id"]),
        "target_type": str(detection["target_type"]),
        "uav": str(detection["uav"]),
        "confidence": float(detection["confidence"]),
        "position": _normalize_position(detection["position"], f"detection '{detection['detection_id']}' position"),
    }


def main(argv=None):
    parser = argparse.ArgumentParser(description="Generate or serve Stage 6B simulation-vision target results")
    parser.add_argument("--config", required=True, type=Path, help="Path to stage6b_sim_vision.json")
    parser.add_argument("--target-types", help="Comma-separated target types to include")
    parser.add_argument("--min-confidence", type=float, help="Minimum confidence threshold")
    parser.add_argument("--backend", choices=("dry-run", "ros"), default="dry-run", help="Provider backend")
    parser.add_argument("--service", default="/mission/target_provider/query", help="ROS Trigger service name")
    parser.add_argument("--output", type=Path, help="Path to write target_results.json in dry-run mode")
    args = parser.parse_args(argv)

    try:
        config = load_config(args.config)
        results = build_results(config, parse_target_types(args.target_types), args.min_confidence)
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
