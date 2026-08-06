#!/usr/bin/env python3
"""Verify the MAVROS odometry plugin TF contract for each namespaced UAV.

MAVROS 1.20.1 odom.cpp performs four static lookups per UAV:

- FCU->ROS (handle_odom):  {map} -> {map}_ned, {child} -> {child}_frd
- ROS->FCU (odom_cb):      {parent}_ned <- header.frame_id,
                           {child}_frd  <- child_frame_id

Lookup failure is logged as "ODOM: Ex" and the plugin continues with an
uninitialized transform, so this gate must pass before any arming.
"""

from __future__ import annotations

import argparse
import json
import re
import sys
import time
from pathlib import Path


def expected_tf_frames(uav_id: str) -> set:
    return {
        f"{uav_id}_map",
        f"{uav_id}_map_ned",
        f"{uav_id}_odom",
        f"{uav_id}_odom_ned",
        f"{uav_id}_camera_init",
        f"{uav_id}_body",
        f"{uav_id}_base_link",
        f"{uav_id}_base_link_frd",
        f"{uav_id}_lidar",
    }


def mavros_lookup_pairs(uav_id: str):
    return [
        (f"{uav_id}_map", f"{uav_id}_map_ned"),
        (f"{uav_id}_base_link", f"{uav_id}_base_link_frd"),
        (f"{uav_id}_odom_ned", f"{uav_id}_camera_init"),
        (f"{uav_id}_base_link_frd", f"{uav_id}_body"),
    ]


def scan_mavros_log_errors(log_text: str, uav_id: str):
    lines = [
        line.strip()
        for line in log_text.splitlines()
        if "ODOM: Ex" in line and (uav_id in line or "ODOM: Ex" in line)
    ]
    return {"count": len(lines), "samples": lines[:3]}


def _load_config(path):
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as exc:
        raise ValueError(f"invalid JSON in {path}: {exc.msg}") from exc


def _validate_config(config):
    uavs = config.get("uavs")
    if not isinstance(uavs, list) or len(uavs) != 2:
        raise ValueError("config must contain exactly two UAV entries")
    for uav in uavs:
        if not uav.get("uav_id") or not uav.get("namespace"):
            raise ValueError("each UAV entry requires uav_id and namespace")


class DryRunChecker:
    def check_uav(self, uav):
        uav_id = uav["uav_id"]
        lookups = [
            {
                "target": target,
                "source": source,
                "status": "planned",
                "ready": True,
            }
            for target, source in mavros_lookup_pairs(uav_id)
        ]
        frames = {frame: "planned" for frame in sorted(expected_tf_frames(uav_id))}
        return {
            "uav_id": uav_id,
            "namespace": uav["namespace"],
            "ready": True,
            "frames": frames,
            "lookups": lookups,
        }


class RosChecker:
    def __init__(self, timeout_s):
        try:
            import rospy
            import tf2_ros
        except ImportError as exc:
            raise RuntimeError(f"ROS contract check requires rospy/tf2_ros: {exc}") from exc
        self.rospy = rospy
        self.tf2_ros = tf2_ros
        self.timeout_s = float(timeout_s)
        if not rospy.core.is_initialized():
            rospy.init_node("future_aircraft_odom_tf_contract_check", anonymous=True)
        self.buffer = tf2_ros.Buffer()
        self.listener = tf2_ros.TransformListener(self.buffer)
        self.wait_start = time.monotonic()

    def _lookup(self, target, source):
        try:
            self.buffer.lookup_transform(target, source, self.rospy.Time(0))
            return {"status": "ok", "detail": None, "ready": True}
        except Exception as exc:
            message = str(exc)
            if "does not exist" in message or "not part of the same tree" in message:
                status = "missing_frame"
            elif "extrapolation" in message:
                status = "extrapolation"
            else:
                status = "error"
            return {"status": status, "detail": message, "ready": False}

    def check_uav(self, uav):
        uav_id = uav["uav_id"]
        lookups = []
        for target, source in mavros_lookup_pairs(uav_id):
            result = self._lookup(target, source)
            lookups.append({"target": target, "source": source, **result})
        frames = {}
        try:
            all_frames = self.buffer.all_frames_as_string()
        except Exception:
            all_frames = ""
        for frame in sorted(expected_tf_frames(uav_id)):
            frames[frame] = "present" if frame in all_frames else "missing"
        return {
            "uav_id": uav_id,
            "namespace": uav["namespace"],
            "ready": all(entry["ready"] for entry in lookups),
            "frames": frames,
            "lookups": lookups,
        }


def build_report(config, backend="dry-run", timeout_s=5.0, mavros_log=None):
    _validate_config(config)
    checker = DryRunChecker() if backend == "dry-run" else RosChecker(timeout_s=timeout_s)
    uav_reports = [checker.check_uav(uav) for uav in sorted(config["uavs"], key=lambda item: item["uav_id"])]
    mavros_log_report = None
    if mavros_log is not None:
        log_text = mavros_log.read_text(encoding="utf-8", errors="replace")
        mavros_log_report = {
            "path": str(mavros_log),
            "uavs": {
                uav["uav_id"]: scan_mavros_log_errors(log_text, uav["uav_id"])
                for uav in config["uavs"]
            },
        }
    ready = all(uav["ready"] for uav in uav_reports)
    if mavros_log_report is not None:
        ready = ready and all(
            item["count"] == 0 for item in mavros_log_report["uavs"].values()
        )
    return {
        "backend": backend,
        "mission_mode": config["mission_mode"],
        "ready": ready,
        "uavs": uav_reports,
        "mavros_log": mavros_log_report,
    }


def write_json(path, value):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value, indent=2, sort_keys=True) + "\n", encoding="utf-8")


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--config", required=True, type=Path)
    parser.add_argument("--backend", choices=("dry-run", "ros"), default="dry-run")
    parser.add_argument("--timeout-s", type=float, default=5.0)
    parser.add_argument("--mavros-log", type=Path, default=None)
    parser.add_argument("--report", required=True, type=Path)
    args = parser.parse_args(argv)
    try:
        report = build_report(
            _load_config(args.config),
            backend=args.backend,
            timeout_s=args.timeout_s,
            mavros_log=args.mavros_log,
        )
        write_json(args.report, report)
        if not report["ready"]:
            print("[ERROR] odom TF contract gate failed", file=sys.stderr)
            return 1
    except Exception as exc:
        print(f"[ERROR] {exc}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
