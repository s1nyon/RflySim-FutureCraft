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


def parse_subscriber_count(system_state, topic):
    """Count real subscribers for a topic from a ROS master system state tuple."""
    _publishers, subscribers, _services = system_state
    for name, connections in subscribers:
        if name == topic:
            return len(connections)
    return 0


def parse_publisher_count(system_state, topic):
    """Count real publishers for a topic from a ROS master system state tuple."""
    publishers, _subscribers, _services = system_state
    for name, connections in publishers:
        if name == topic:
            return len(connections)
    return 0


def depth_image_stats(data):
    """Return mono16 little-endian depth statistics for a raw image buffer."""
    if not data:
        return {"zero_ratio": 1.0, "min_depth": None, "max_depth": None}
    values = []
    for index in range(0, len(data) - 1, 2):
        values.append(data[index] | (data[index + 1] << 8))
    nonzero = sum(1 for value in values if value != 0)
    return {
        "zero_ratio": round((len(values) - nonzero) / len(values), 4),
        "min_depth": min(values),
        "max_depth": max(values),
    }


def summarize_depth_flow(samples, now, duration_s):
    """Summarize measured mono16 depth image flow from ROS samples."""
    if not samples:
        return {
            "count": 0,
            "receive_rate_hz": 0.0,
            "header_rate_hz": None,
            "stamp_monotonic": True,
            "any_nonzero_sample": False,
            "encoding": None,
            "width": None,
            "height": None,
            "last_zero_ratio": None,
            "last_min_depth": None,
            "last_max_depth": None,
            "last_age_s": None,
        }
    receive_times = [float(sample["receive"]) for sample in samples]
    headers = [
        float(sample["header_stamp"])
        for sample in samples
        if sample.get("header_stamp") is not None
    ]

    def frame_stats(sample):
        return sample.get("stats") or depth_image_stats(sample.get("data") or b"")

    last = samples[-1]
    last_stats = frame_stats(last)
    return {
        "count": len(receive_times),
        "receive_rate_hz": round(
            len(receive_times) / max(float(duration_s), 1e-6), 2
        ),
        "header_rate_hz": (
            round((len(headers) - 1) / max(headers[-1] - headers[0], 1e-6), 2)
            if len(headers) >= 2 and headers[-1] > headers[0]
            else None
        ),
        "stamp_monotonic": all(
            headers[index] <= headers[index + 1]
            for index in range(len(headers) - 1)
        ),
        "any_nonzero_sample": any(
            frame_stats(sample).get("max_depth") not in (None, 0)
            for sample in samples
        ),
        "encoding": last.get("encoding"),
        "width": last.get("width"),
        "height": last.get("height"),
        "last_zero_ratio": last_stats["zero_ratio"],
        "last_min_depth": last_stats["min_depth"],
        "last_max_depth": last_stats["max_depth"],
        "last_age_s": round(now - receive_times[-1], 3),
    }


def summarize_message_flow(sample_times, now):
    """Summarize measured message flow from receive-time samples."""
    if not sample_times:
        return {"count": 0, "first_latency_s": None, "last_age_s": None}
    return {
        "count": len(sample_times),
        "first_latency_s": round(float(sample_times[0]), 3),
        "last_age_s": round(float(now) - float(sample_times[-1]), 3),
    }


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
    for field in ("raw_rgb_topic", "raw_bottom_topic", "raw_depth_topic", "depth_topic"):
        for bridge in bridges:
            if not bridge.get(field):
                raise ValueError(f"fast_lio.bridges missing required field '{field}'")
    for field in (
        "copter_id",
        "sensor_seq_id",
        "udp_port",
        "raw_lidar_topic",
        "raw_rgb_topic",
        "raw_bottom_topic",
        "raw_depth_topic",
        "raw_imu_topic",
        "lidar_topic",
        "imu_topic",
        "depth_topic",
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
            "sensor_rgb_topic",
            "sensor_bottom_topic",
            "sensor_depth_topic",
            "planner_depth_topic",
            "slam_odom_topic",
            "slam_cloud_topic",
            "slam_odom_to_fcu_topic",
            "planner_cmd_topic",
            "planner_goal_topic",
            "mavros_state_topic",
            "mavros_feedback_odom_topic",
            "mavros_setpoint_topic",
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
    if len({uav.get("sensor_depth_topic") for uav in uavs}) != 2:
        raise ValueError("uavs must have distinct sensor_depth_topic")


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
                "topic_publisher_count",
                "depth_publisher_count",
                uav["sensor_depth_topic"],
                min_count=1,
                max_count=1,
            ),
            _planned(
                "depth_image_flow",
                "depth_flow",
                uav["sensor_depth_topic"],
                duration_s=5.0,
                min_rate_hz=20,
                max_rate_hz=45,
                expected_encoding="mono16",
                expected_width=640,
                expected_height=480,
            ),
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
            _planned(
                "topic_subscriber_count",
                "planner_goal_subscribers",
                uav["planner_goal_topic"],
                min_count=1,
            ),
            _planned(
                "topic_message_flow",
                "planner_cmd_flow",
                uav["planner_cmd_topic"],
                duration_s=3.0,
                min_messages=1,
            ),
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


def _planned(kind, name, target, **extra):
    check = {
        "kind": kind,
        "name": name,
        "target": target,
    }
    check.update(extra)
    return check


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
        if kind == "topic_publisher_count":
            return self._wait_for_publisher_count(check)
        if kind == "topic_subscriber_count":
            return self._wait_for_subscribers(check)
        if kind == "topic_message_flow":
            return self._measure_message_flow(check)
        if kind == "depth_image_flow":
            return self._measure_depth_image_flow(check)
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

    def _wait_for_publisher_count(self, check):
        result = dict(check)
        deadline = time.monotonic() + self.timeout_s
        last_count = 0
        min_count = int(check.get("min_count", 1))
        max_count = int(check.get("max_count", min_count))
        while time.monotonic() < deadline and not self.rospy.is_shutdown():
            try:
                _code, _status, system_state = self.rospy.get_master().getSystemState()
            except Exception as exc:
                result["status"] = "master_unavailable"
                result["ready"] = False
                result["detail"] = str(exc)
                return result
            last_count = parse_publisher_count(system_state, check["target"])
            if min_count <= last_count <= max_count:
                result["status"] = "publishers_present"
                result["ready"] = True
                result["publisher_count"] = last_count
                return result
            time.sleep(0.2)
        result["status"] = "publisher_count_unexpected"
        result["ready"] = False
        result["publisher_count"] = last_count
        result["detail"] = (
            f"observed {last_count} publishers for {check['target']}; "
            f"expected {min_count}-{max_count}"
        )
        return result

    def _wait_for_subscribers(self, check):
        result = dict(check)
        deadline = time.monotonic() + self.timeout_s
        last_count = 0
        while time.monotonic() < deadline and not self.rospy.is_shutdown():
            try:
                _code, _status, system_state = self.rospy.get_master().getSystemState()
            except Exception as exc:
                result["status"] = "master_unavailable"
                result["ready"] = False
                result["detail"] = str(exc)
                return result
            last_count = parse_subscriber_count(system_state, check["target"])
            if last_count >= int(check.get("min_count", 1)):
                result["status"] = "subscribers_present"
                result["ready"] = True
                result["subscriber_count"] = last_count
                return result
            time.sleep(0.2)
        result["status"] = "no_subscribers"
        result["ready"] = False
        result["subscriber_count"] = last_count
        result["detail"] = f"observed {last_count} subscribers for {check['target']}"
        return result

    def _measure_message_flow(self, check):
        result = dict(check)
        duration_s = float(check.get("duration_s", 3.0))
        min_messages = int(check.get("min_messages", 1))
        samples = []
        deadline = time.monotonic() + duration_s
        while time.monotonic() < deadline and not self.rospy.is_shutdown():
            remaining = max(0.01, deadline - time.monotonic())
            try:
                self.rospy.wait_for_message(
                    check["target"], self.rospy.AnyMsg, timeout=min(0.5, remaining)
                )
                samples.append(time.monotonic())
            except Exception:
                pass
        summary = summarize_message_flow(samples, now=time.monotonic())
        result.update(summary)
        if (
            summary["count"] >= min_messages
            and summary["last_age_s"] is not None
            and summary["last_age_s"] <= duration_s
        ):
            result["status"] = "message_flow_ok"
            result["ready"] = True
        else:
            result["status"] = "message_flow_empty"
            result["ready"] = False
            result["detail"] = f"expected at least {min_messages} message(s) in {duration_s:.1f}s"
        return result

    def _measure_depth_image_flow(self, check):
        from sensor_msgs.msg import Image

        result = dict(check)
        duration_s = float(check.get("duration_s", 5.0))
        min_count = int(check.get("min_messages", 1))
        max_samples = int(check.get("max_samples", 200))
        expected_encoding = str(check.get("expected_encoding", "mono16"))
        expected_width = int(check.get("expected_width", 640))
        expected_height = int(check.get("expected_height", 480))
        min_rate_hz = float(check.get("min_rate_hz", 20.0))
        max_rate_hz = float(check.get("max_rate_hz", 45.0))
        samples = []
        deadline = time.monotonic() + duration_s
        while time.monotonic() < deadline and not self.rospy.is_shutdown():
            remaining = max(0.01, deadline - time.monotonic())
            try:
                message = self.rospy.wait_for_message(
                    check["target"], Image, timeout=min(0.5, remaining)
                )
            except Exception:
                continue
            header = message.header.stamp
            data = bytes(message.data)
            samples.append(
                {
                    "receive": time.monotonic(),
                    "header_stamp": header.secs + header.nsecs * 1e-9,
                    "stats": depth_image_stats(data),
                    "encoding": str(message.encoding),
                    "width": int(message.width),
                    "height": int(message.height),
                }
            )
            if len(samples) > max_samples:
                samples.pop(0)
        summary = summarize_depth_flow(
            samples, now=time.monotonic(), duration_s=duration_s
        )
        result.update(summary)
        errors = []
        if summary["count"] < min_count:
            errors.append(
                f"expected at least {min_count} depth image(s) in {duration_s:.1f}s"
            )
        if not (min_rate_hz <= summary["receive_rate_hz"] <= max_rate_hz):
            errors.append(
                f"depth rate {summary['receive_rate_hz']} Hz outside "
                f"{min_rate_hz}-{max_rate_hz} Hz"
            )
        if not summary["stamp_monotonic"]:
            errors.append("depth header stamps are not monotonic")
        if summary["encoding"] != expected_encoding:
            errors.append(
                f"expected encoding {expected_encoding}, got {summary['encoding']}"
            )
        if summary["width"] != expected_width or summary["height"] != expected_height:
            errors.append(
                f"expected {expected_width}x{expected_height}, "
                f"got {summary['width']}x{summary['height']}"
            )
        if not summary["any_nonzero_sample"]:
            errors.append("depth image samples are all zero")
        result["status"] = "depth_flow_ok" if not errors else "depth_flow_bad"
        result["ready"] = not errors
        if errors:
            result["detail"] = "; ".join(errors)
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
