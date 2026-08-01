#!/usr/bin/env python3
"""Readiness check for the Stage 7 FAST-LIO, ego-swarm, and MAVROS live loop."""

import argparse
import json
import os
import socket
import sys
import time
from pathlib import Path


REQUIRED_UAVS = {
    "uav1": "/uav1",
    "uav2": "/uav2",
}

REQUIRED_FIELDS = (
    "uav_id",
    "namespace",
    "slam_odom_topic",
    "slam_odom_to_fcu_topic",
    "planner_cmd_topic",
    "mavros_state_topic",
    "mavros_setpoint_topic",
    "mavros_set_mode_service",
    "mavros_arming_service",
)


def load_config(path):
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as exc:
        raise ValueError(f"invalid JSON in {path}: {exc.msg}") from exc


def validate_config(config):
    if not isinstance(config, dict):
        raise ValueError("stage7 config must be an object")
    if config.get("mission_mode") != "live_slam_ego_swarm_flight":
        raise ValueError("mission_mode must be 'live_slam_ego_swarm_flight'")

    policy = config.get("simulation_arm_policy")
    if not isinstance(policy, dict):
        raise ValueError("stage7 config missing simulation_arm_policy")
    if policy.get("mode") != "simulation_only":
        raise ValueError("simulation_arm_policy.mode must be 'simulation_only'")
    for flag in ("--allow-arm", "--simulation-only"):
        if flag not in policy.get("required_flags", []):
            raise ValueError(f"simulation_arm_policy.required_flags missing {flag}")

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
        if uav["slam_odom_topic"] != uav["slam_odom_to_fcu_topic"]:
            raise ValueError(f"uavs[{index}] must use the FAST-LIO odometry topic as MAVROS external odometry")

    if observed != REQUIRED_UAVS:
        raise ValueError("uavs must be exactly uav1:/uav1 and uav2:/uav2")


def _validate_namespace_binding(uav, index):
    namespace = uav["namespace"]
    for field in REQUIRED_FIELDS:
        if field == "uav_id":
            continue
        value = uav[field]
        if field == "namespace":
            if value != namespace:
                raise ValueError(f"uavs[{index}].namespace mismatch")
            continue
        if not value.startswith(namespace + "/"):
            raise ValueError(f"uavs[{index}] {field} must be under namespace '{namespace}'")


def build_report(config, backend="dry-run", timeout_s=5.0):
    validate_config(config)
    checker = DryRunChecker() if backend == "dry-run" else RosChecker(timeout_s=timeout_s)
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
        "uavs": uav_reports,
    }


class DryRunChecker:
    def check_uav(self, uav):
        return [
            _check("inbound_topic", "mavros_state_topic", uav["mavros_state_topic"], "planned", True),
            _check("inbound_topic", "slam_odom_topic", uav["slam_odom_topic"], "planned", True),
            _check("inbound_topic", "planner_cmd_topic", uav["planner_cmd_topic"], "planned", True),
            _check("outbound_topic", "mavros_setpoint_topic", uav["mavros_setpoint_topic"], "configured", True),
            _check("service", "mavros_set_mode_service", uav["mavros_set_mode_service"], "planned", True),
            _check("service", "mavros_arming_service", uav["mavros_arming_service"], "planned", True),
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
            rospy.init_node("future_aircraft_stage7_flight_smoke_check", anonymous=True)
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
            self._wait_for_topic("mavros_state_topic", uav["mavros_state_topic"]),
            self._wait_for_topic("slam_odom_topic", uav["slam_odom_topic"]),
            self._wait_for_topic_advertised("planner_cmd_topic", uav["planner_cmd_topic"]),
            _check("outbound_topic", "mavros_setpoint_topic", uav["mavros_setpoint_topic"], "configured", True),
            self._wait_for_service("mavros_set_mode_service", uav["mavros_set_mode_service"]),
            self._wait_for_service("mavros_arming_service", uav["mavros_arming_service"]),
        ]

    def _wait_for_topic(self, name, target):
        try:
            self.rospy.wait_for_message(target, self.rospy.AnyMsg, timeout=self.timeout_s)
            return _check("inbound_topic", name, target, "available", True)
        except Exception as exc:
            return _check("inbound_topic", name, target, "unavailable", False, str(exc))

    def _wait_for_topic_advertised(self, name, target):
        deadline = time.monotonic() + self.timeout_s
        last_topics = []
        while time.monotonic() < deadline and not self.rospy.is_shutdown():
            try:
                last_topics = [topic for topic, _topic_type in self.rospy.get_published_topics()]
            except Exception as exc:
                return _check("advertised_topic", name, target, "unavailable", False, str(exc))
            if target in last_topics:
                return _check("advertised_topic", name, target, "available", True)
            time.sleep(0.2)
        return _check(
            "advertised_topic",
            name,
            target,
            "unavailable",
            False,
            f"not advertised within {self.timeout_s:.1f}s; observed {len(last_topics)} topics",
        )

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
    parser = argparse.ArgumentParser(description="Stage 7 live FAST-LIO and ego-swarm smoke check")
    parser.add_argument("--config", required=True, type=Path, help="Path to stage7_live_slam_ego_swarm.json")
    parser.add_argument("--backend", choices=("dry-run", "ros"), default="dry-run", help="Smoke check backend")
    parser.add_argument("--timeout-s", type=float, default=5.0, help="ROS topic/service wait timeout")
    parser.add_argument("--report", required=True, type=Path, help="Path to write the smoke report JSON")
    args = parser.parse_args(argv)

    try:
        config = load_config(args.config)
        report = build_report(config, backend=args.backend, timeout_s=args.timeout_s)
        write_json(args.report, report)
        if not report["ready"]:
            print("[ERROR] one or more Stage 7 smoke checks failed", file=sys.stderr)
            return 1
    except Exception as exc:
        print(f"[ERROR] {exc}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
