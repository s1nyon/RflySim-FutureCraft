#!/usr/bin/env python3
"""Layered read-only probe for Stage 7 live bring-up."""

import argparse
import json
import os
import socket
import sys
import time
from pathlib import Path


LAYERS = ("sensor_bridge", "fast_lio", "mavros", "ego_swarm", "flight_gate")


def evaluate_saved_readiness(report, run_id, simulation_instance_id, max_age_sec, now):
    from stage7_sensor_readiness import validate_report

    if report is None:
        errors = ["readiness report is unavailable"]
    else:
        errors = validate_report(
            report, run_id, simulation_instance_id, max_age_sec, now
        )
    return {
        "kind": "readiness_report",
        "name": "isolated_sensor_readiness",
        "target": "current_run_scoped_report",
        "ready": not errors,
        "status": "readiness_accepted" if not errors else "readiness_rejected",
        "detail": "; ".join(errors),
    }


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
    uavs = config.get("uavs")
    bridges = config.get("fast_lio", {}).get("bridges")
    if not isinstance(bridges, list) or len(bridges) != 2:
        raise ValueError("stage7 config must contain two fast_lio.bridges entries")
    bridge_by_uav = {bridge.get("uav_id"): bridge for bridge in bridges}
    if set(bridge_by_uav) != {"uav1", "uav2"}:
        raise ValueError("fast_lio.bridges must identify uav1 and uav2")
    for field in (
        "copter_id",
        "sensor_seq_id",
        "udp_port",
        "raw_lidar_topic",
        "raw_imu_topic",
        "lidar_topic",
        "imu_topic",
        "identity_topic",
    ):
        if len({bridge.get(field) for bridge in bridges}) != 2:
            raise ValueError(f"fast_lio.bridges must have distinct {field}")
    if not isinstance(uavs, list) or len(uavs) != 2:
        raise ValueError("stage7 config must contain two UAV entries")
    for index, uav in enumerate(uavs):
        for field in (
            "uav_id",
            "namespace",
            "sensor_lidar_topic",
            "sensor_imu_topic",
            "slam_odom_topic",
            "slam_cloud_topic",
            "slam_odom_to_fcu_topic",
            "planner_cmd_topic",
            "planner_goal_topic",
            "mavros_state_topic",
            "mavros_feedback_odom_topic",
            "mavros_set_mode_service",
            "mavros_arming_service",
        ):
            if not uav.get(field):
                raise ValueError(f"uavs[{index}] missing required field '{field}'")
        namespace = uav["namespace"]
        for field, value in uav.items():
            if field == "uav_id" or not isinstance(value, str) or not value.startswith("/"):
                continue
            if field == "namespace":
                if value != namespace:
                    raise ValueError(f"uavs[{index}].namespace mismatch: {value}")
                continue
            if not value.startswith(namespace + "/"):
                raise ValueError(f"uavs[{index}].{field} must be under {namespace}: {value}")
        bridge = bridge_by_uav.get(uav["uav_id"])
        if bridge is None:
            raise ValueError(f"uavs[{index}] has no matching fast_lio bridge")
        if uav["sensor_lidar_topic"] != bridge["lidar_topic"]:
            raise ValueError(f"uavs[{index}].sensor_lidar_topic must use normalized bridge output")
        if uav["sensor_imu_topic"] != bridge["imu_topic"]:
            raise ValueError(f"uavs[{index}].sensor_imu_topic must use normalized bridge output")


def build_report(
    config,
    backend="dry-run",
    timeout_s=3.0,
    readiness_report=None,
    run_id=None,
    simulation_instance_id=None,
    readiness_max_age_s=30.0,
):
    validate_config(config)
    checker = (
        DryRunChecker()
        if backend == "dry-run"
        else RosChecker(
            timeout_s=timeout_s,
            readiness_report=readiness_report,
            run_id=run_id,
            simulation_instance_id=simulation_instance_id,
            readiness_max_age_s=readiness_max_age_s,
        )
    )
    uav_reports = []
    layer_checks = {layer: [] for layer in LAYERS}
    bridge_by_uav = {
        bridge["uav_id"]: bridge for bridge in config["fast_lio"]["bridges"]
    }

    for uav in sorted(config["uavs"], key=lambda item: item["uav_id"]):
        report = {
            "uav_id": uav["uav_id"],
            "namespace": uav["namespace"],
            "layers": {},
        }
        for layer, checks in _checks_for_uav(uav, bridge_by_uav[uav["uav_id"]], config).items():
            results = [checker.evaluate(check) for check in checks]
            report["layers"][layer] = {
                "ready": all(item["ready"] for item in results),
                "checks": results,
            }
            layer_checks[layer].extend(results)
        report["ready"] = all(layer["ready"] for layer in report["layers"].values())
        uav_reports.append(report)

    layers = {
        layer: {
            "ready": all(item["ready"] for item in checks),
            "checks": checks,
        }
        for layer, checks in layer_checks.items()
    }
    readiness_ready = any(
        check.get("kind") == "readiness_report" and check.get("ready")
        for check in layers["flight_gate"]["checks"]
    )
    if backend == "ros" and not readiness_ready:
        layers["ego_swarm"]["ready"] = False
        layers["flight_gate"]["ready"] = False
        for uav_report in uav_reports:
            uav_report["layers"]["ego_swarm"]["ready"] = False
            uav_report["layers"]["flight_gate"]["ready"] = False
            uav_report["ready"] = False

    return {
        "backend": backend,
        "mission_mode": config["mission_mode"],
        "ready": all(layer["ready"] for layer in layers.values()),
        "layers": layers,
        "uavs": uav_reports,
    }


def _checks_for_uav(uav, bridge, config):
    policy = config.get("simulation_arm_policy", {})
    return {
        "sensor_bridge": [
            _planned("topic_message", "identity", bridge["identity_topic"]),
            _planned("topic_message", "raw_lidar", bridge["raw_lidar_topic"]),
            _planned("topic_message", "raw_imu", bridge["raw_imu_topic"]),
            _planned("topic_message", "normalized_lidar", bridge["lidar_topic"]),
            _planned("topic_message", "normalized_imu", bridge["imu_topic"]),
            _planned(
                "topic_message",
                "adapter_diagnostics",
                bridge.get(
                    "diagnostics_topic", f"/{uav['uav_id']}/rflysim/adapter_diagnostics"
                ),
            ),
        ],
        "fast_lio": [
            _planned("topic_message", "slam_odom_to_fcu", uav["slam_odom_to_fcu_topic"]),
            _planned("topic_message", "slam_cloud", uav["slam_cloud_topic"]),
        ],
        "mavros": [
            _planned("topic_message", "state", uav["mavros_state_topic"]),
            _planned("topic_message", "feedback_odom", uav["mavros_feedback_odom_topic"]),
            _planned("service", "set_mode", uav["mavros_set_mode_service"]),
            _planned("service", "arming", uav["mavros_arming_service"]),
        ],
        "ego_swarm": [
            _planned("topic_advertised", "planner_cmd", uav["planner_cmd_topic"]),
            _planned("topic_ready_for_publish", "planner_goal", uav["planner_goal_topic"]),
        ],
        "flight_gate": [
            {
                "kind": "config_gate",
                "name": "simulation_arm_policy",
                "target": "simulation_only",
                "expected": {
                    "allow_arm": True,
                    "mode": "simulation_only",
                    "required_flags": ["--allow-arm", "--simulation-only"],
                },
                "observed": policy,
            },
            _planned("readiness_report", "isolated_sensor_readiness", "current_run_scoped_report"),
        ],
    }


def _planned(kind, name, target):
    return {
        "kind": kind,
        "name": name,
        "target": target,
    }


class DryRunChecker:
    def evaluate(self, check):
        result = dict(check)
        result["status"] = "planned"
        result["ready"] = True
        return result


class RosChecker:
    def __init__(
        self,
        timeout_s,
        readiness_report,
        run_id,
        simulation_instance_id,
        readiness_max_age_s,
    ):
        try:
            import rospy
        except ImportError as exc:
            raise RuntimeError(f"ROS probe requires rospy: {exc}") from exc

        self.rospy = rospy
        self.timeout_s = float(timeout_s)
        self.readiness_report = readiness_report
        self.run_id = run_id
        self.simulation_instance_id = simulation_instance_id
        self.readiness_max_age_s = float(readiness_max_age_s)
        if not rospy.core.is_initialized():
            rospy.init_node("future_aircraft_stage7_topic_probe", anonymous=True)
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

    def evaluate(self, check):
        kind = check["kind"]
        if kind == "topic_message":
            return self._wait_for_message(check)
        if kind == "topic_advertised":
            return self._wait_for_advertised_topic(check)
        if kind == "topic_ready_for_publish":
            return self._topic_ready_for_publish(check)
        if kind == "service":
            return self._wait_for_service(check)
        if kind == "config_gate":
            return self._evaluate_gate(check)
        if kind == "readiness_report":
            return evaluate_saved_readiness(
                self.readiness_report,
                self.run_id,
                self.simulation_instance_id,
                self.readiness_max_age_s,
                time.time(),
            )
        raise ValueError(f"unsupported check kind '{kind}'")

    def _wait_for_message(self, check):
        result = dict(check)
        try:
            self.rospy.wait_for_message(check["target"], self.rospy.AnyMsg, timeout=self.timeout_s)
            result["status"] = "message_available"
            result["ready"] = True
        except Exception as exc:
            result["status"] = "message_unavailable"
            result["ready"] = False
            result["detail"] = str(exc)
        return result

    def _wait_for_advertised_topic(self, check):
        result = dict(check)
        deadline = time.monotonic() + self.timeout_s
        last_count = 0
        while time.monotonic() < deadline and not self.rospy.is_shutdown():
            topics = [topic for topic, _topic_type in self.rospy.get_published_topics()]
            last_count = len(topics)
            if check["target"] in topics:
                result["status"] = "topic_advertised"
                result["ready"] = True
                return result
            time.sleep(0.2)
        result["status"] = "topic_not_advertised"
        result["ready"] = False
        result["detail"] = f"observed {last_count} published topics"
        return result

    def _topic_ready_for_publish(self, check):
        result = dict(check)
        result["status"] = "publisher_can_be_created"
        result["ready"] = True
        return result

    def _wait_for_service(self, check):
        result = dict(check)
        try:
            self.rospy.wait_for_service(check["target"], timeout=self.timeout_s)
            result["status"] = "service_available"
            result["ready"] = True
        except Exception as exc:
            result["status"] = "service_unavailable"
            result["ready"] = False
            result["detail"] = str(exc)
        return result

    def _evaluate_gate(self, check):
        result = dict(check)
        result["ready"] = _gate_ready(check["observed"])
        result["status"] = "gate_ready" if result["ready"] else "gate_not_ready"
        return result


def _gate_ready(policy):
    return (
        isinstance(policy, dict)
        and policy.get("allow_arm") is True
        and policy.get("mode") == "simulation_only"
        and "--allow-arm" in policy.get("required_flags", [])
        and "--simulation-only" in policy.get("required_flags", [])
    )


def write_json(path, value):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value, indent=2, sort_keys=True) + "\n", encoding="utf-8")


def main(argv=None):
    parser = argparse.ArgumentParser(description="Stage 7 layered topic and service probe")
    parser.add_argument("--config", required=True, type=Path, help="Path to stage7_live_slam_ego_swarm.json")
    parser.add_argument("--backend", choices=("dry-run", "ros"), default="dry-run", help="Probe backend")
    parser.add_argument("--timeout-s", type=float, default=3.0, help="ROS wait timeout for each check")
    parser.add_argument("--report", required=True, type=Path, help="Path to write the probe report")
    parser.add_argument("--readiness-report", type=Path, help="Current run-scoped sensor readiness report")
    parser.add_argument("--run-id", help="Expected Stage 7 run ID")
    parser.add_argument("--simulation-instance-id", help="Expected simulator instance ID")
    parser.add_argument("--readiness-max-age-s", type=float, default=30.0)
    args = parser.parse_args(argv)

    try:
        readiness_report = None
        if args.readiness_report and args.readiness_report.exists():
            readiness_report = load_config(args.readiness_report)
        report = build_report(
            load_config(args.config),
            backend=args.backend,
            timeout_s=args.timeout_s,
            readiness_report=readiness_report,
            run_id=args.run_id,
            simulation_instance_id=args.simulation_instance_id,
            readiness_max_age_s=args.readiness_max_age_s,
        )
        write_json(args.report, report)
        if not report["ready"]:
            print("[ERROR] one or more Stage 7 probe layers are not ready", file=sys.stderr)
            return 1
    except Exception as exc:
        print(f"[ERROR] {exc}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
