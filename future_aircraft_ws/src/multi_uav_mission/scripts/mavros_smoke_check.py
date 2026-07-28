#!/usr/bin/env python3
"""Read-only MAVROS readiness smoke check for the Stage 5 live mission boundary."""

import argparse
import json
import os
import socket
import sys
from pathlib import Path


REQUIRED_UAVS = {
    "uav1": "/uav1",
    "uav2": "/uav2",
}

REQUIRED_FIELDS = (
    "uav_id",
    "namespace",
    "state_topic",
    "odom_topic",
    "setpoint_topic",
    "set_mode_service",
    "arming_service",
    "planner_goal_topic",
)


def load_config(path):
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as exc:
        raise ValueError(f"invalid JSON in {path}: {exc.msg}") from exc


def validate_config(config):
    if not isinstance(config, dict):
        raise ValueError("live config must be an object")
    if config.get("mission_mode") != "live_ros_boundary":
        raise ValueError("mission_mode must be 'live_ros_boundary'")
    if float(config.get("setpoint_rate_hz", 0)) < 20:
        raise ValueError("setpoint_rate_hz must be at least 20")

    uavs = config.get("uavs")
    if not isinstance(uavs, list) or len(uavs) != 2:
        raise ValueError("uavs must contain exactly uav1 and uav2")

    observed = {}
    for index, uav in enumerate(uavs):
        if not isinstance(uav, dict):
            raise ValueError(f"uavs[{index}] must be an object")
        for field in REQUIRED_FIELDS:
            if not uav.get(field):
                raise ValueError(f"uavs[{index}] missing required field '{field}'")
        uav_id = uav["uav_id"]
        namespace = uav["namespace"]
        if uav_id in observed:
            raise ValueError(f"duplicate UAV id '{uav_id}'")
        observed[uav_id] = namespace
        _validate_namespace_binding(uav, index)

    if observed != REQUIRED_UAVS:
        raise ValueError("uavs must be exactly uav1:/uav1 and uav2:/uav2")


def _validate_namespace_binding(uav, index):
    namespace = uav["namespace"]
    for field in ("state_topic", "odom_topic", "setpoint_topic", "set_mode_service", "arming_service", "planner_goal_topic"):
        value = uav[field]
        if not value.startswith(namespace + "/"):
            raise ValueError(f"uavs[{index}] {field} must be under namespace '{namespace}'")


def build_report(config, backend="dry-run", timeout_s=5.0):
    validate_config(config)
    if backend == "dry-run":
        checker = DryRunChecker()
    elif backend == "ros":
        checker = RosChecker(timeout_s=timeout_s)
    else:
        raise ValueError(f"unsupported backend '{backend}'")

    uav_reports = []
    for uav in sorted(config["uavs"], key=lambda item: item["uav_id"]):
        checks = checker.check_uav(uav)
        uav_reports.append(
            {
                "uav_id": uav["uav_id"],
                "namespace": uav["namespace"],
                "ready": all(check["ready"] for check in checks),
                "checks": checks,
            }
        )

    return {
        "backend": backend,
        "mission_mode": config["mission_mode"],
        "ready": all(uav["ready"] for uav in uav_reports),
        "setpoint_rate_hz": config["setpoint_rate_hz"],
        "uavs": uav_reports,
    }


class DryRunChecker:
    def check_uav(self, uav):
        return [
            _check("inbound_topic", "state_topic", uav["state_topic"], "planned", True),
            _check("inbound_topic", "odom_topic", uav["odom_topic"], "planned", True),
            _check("outbound_topic", "setpoint_topic", uav["setpoint_topic"], "configured", True),
            _check("service", "set_mode_service", uav["set_mode_service"], "planned", True),
            _check("service", "arming_service", uav["arming_service"], "planned", True),
            _check("outbound_topic", "planner_goal_topic", uav["planner_goal_topic"], "configured", True),
        ]


class RosChecker:
    def __init__(self, timeout_s):
        try:
            import rospy
        except ImportError as exc:
            raise RuntimeError(f"ROS smoke check requires rospy: {exc}") from exc

        self.rospy = rospy
        self.timeout_s = float(timeout_s)
        if not rospy.core.is_initialized():
            rospy.init_node("future_aircraft_mavros_smoke_check", anonymous=True)
        self._verify_ros_master()

    def _verify_ros_master(self):
        previous_timeout = socket.getdefaulttimeout()
        socket.setdefaulttimeout(self.timeout_s)
        try:
            self.rospy.get_master().getPid()
        except Exception as exc:
            master_uri = os.environ.get("ROS_MASTER_URI", "http://localhost:11311")
            raise RuntimeError(f"ROS master unavailable at {master_uri}: {exc}") from exc
        finally:
            socket.setdefaulttimeout(previous_timeout)

    def check_uav(self, uav):
        return [
            self._wait_for_topic("state_topic", uav["state_topic"]),
            self._wait_for_topic("odom_topic", uav["odom_topic"]),
            _check("outbound_topic", "setpoint_topic", uav["setpoint_topic"], "configured", True),
            self._wait_for_service("set_mode_service", uav["set_mode_service"]),
            self._wait_for_service("arming_service", uav["arming_service"]),
            _check("outbound_topic", "planner_goal_topic", uav["planner_goal_topic"], "configured", True),
        ]

    def _wait_for_topic(self, name, target):
        try:
            self.rospy.wait_for_message(target, self.rospy.AnyMsg, timeout=self.timeout_s)
            return _check("inbound_topic", name, target, "available", True)
        except Exception as exc:
            return _check("inbound_topic", name, target, "unavailable", False, str(exc))

    def _wait_for_service(self, name, target):
        try:
            self.rospy.wait_for_service(target, timeout=self.timeout_s)
            return _check("service", name, target, "available", True)
        except Exception as exc:
            return _check("service", name, target, "unavailable", False, str(exc))


def _check(kind, name, target, status, ready, detail=None):
    result = {
        "kind": kind,
        "name": name,
        "target": target,
        "status": status,
        "ready": ready,
    }
    if detail:
        result["detail"] = detail
    return result


def write_json(path, value):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value, indent=2, sort_keys=True) + "\n", encoding="utf-8")


def main(argv=None):
    parser = argparse.ArgumentParser(description="Read-only MAVROS smoke check for future_aircraft_sim")
    parser.add_argument("--live-config", required=True, type=Path, help="Path to stage5_live_mission.json")
    parser.add_argument("--backend", choices=("dry-run", "ros"), default="dry-run", help="Smoke check backend")
    parser.add_argument("--timeout-s", type=float, default=5.0, help="ROS topic/service wait timeout")
    parser.add_argument("--report", required=True, type=Path, help="Path to write mavros_smoke_report.json")
    args = parser.parse_args(argv)

    try:
        config = load_config(args.live_config)
        report = build_report(config, backend=args.backend, timeout_s=args.timeout_s)
        write_json(args.report, report)
        if not report["ready"]:
            print("[ERROR] one or more MAVROS smoke checks failed", file=sys.stderr)
            return 1
    except Exception as exc:
        print(f"[ERROR] {exc}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
