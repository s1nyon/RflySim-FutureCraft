#!/usr/bin/env python3
"""Fail-closed Stage 7 dual-sensor readiness report generation and validation."""

import argparse
import json
import math
from pathlib import Path
import struct
import sys
import time


GATE_NAMES = (
    "identity",
    "schema",
    "freshness",
    "isolation",
    "stationary_stability",
)
REQUIRED_CLOUD_FIELDS = (
    "x",
    "y",
    "z",
    "intensity",
    "t",
    "reflectivity",
    "ring",
    "ambient",
    "range",
)
DEFAULT_LIMITS = {
    "minimum_observation_sec": 5.0,
    "maximum_position_delta_m": 0.15,
    "maximum_velocity_mps": 0.1,
    "maximum_attitude_delta_rad": 0.1,
}


def _number(value):
    return isinstance(value, (int, float)) and not isinstance(value, bool) and math.isfinite(value)


def _strictly_increasing(values):
    return (
        isinstance(values, list)
        and len(values) >= 2
        and all(_number(value) for value in values)
        and all(right > left for left, right in zip(values, values[1:]))
    )


def _duplicates(values):
    seen = set()
    duplicates = set()
    for value in values:
        if value in seen:
            duplicates.add(value)
        seen.add(value)
    return duplicates


def validate_report(report, expected_run_id, expected_instance_id, max_age_sec, now):
    """Return every reason a saved report cannot authorize later Stage 7 work."""
    errors = []
    if not isinstance(report, dict):
        return ["report must be an object"]
    if report.get("backend") != "ros":
        errors.append("live evidence not executed")
    if report.get("run_id") != expected_run_id:
        errors.append("run id mismatch")
    if report.get("simulation_instance_id") != expected_instance_id:
        errors.append("simulation instance mismatch")

    created_at = report.get("created_at")
    if not _number(created_at) or not _number(now) or not _number(max_age_sec) or max_age_sec <= 0:
        errors.append("invalid report freshness metadata")
    elif now < created_at:
        errors.append("report timestamp is in the future")
    elif now - created_at > max_age_sec:
        errors.append("stale report")

    gates = report.get("gates")
    if not isinstance(gates, dict):
        errors.append("missing readiness gates")
    else:
        for gate in GATE_NAMES:
            if gates.get(gate) != "pass":
                errors.append(f"readiness gate did not pass: {gate}")
    if report.get("ready") is not True:
        errors.append("report ready flag is not true")

    limits = report.get("limits")
    if not isinstance(limits, dict):
        errors.append("missing stationary limits")
        limits = DEFAULT_LIMITS
    else:
        for name, safety_limit in DEFAULT_LIMITS.items():
            value = limits.get(name)
            if not _number(value) or value <= 0:
                errors.append(f"invalid stationary limit: {name}")
                continue
            if name == "minimum_observation_sec" and value < safety_limit:
                errors.append(f"unsafe readiness limit: {name}")
            if name != "minimum_observation_sec" and value > safety_limit:
                errors.append(f"unsafe readiness limit: {name}")

    vehicles = report.get("vehicles")
    if not isinstance(vehicles, list) or len(vehicles) != 2:
        errors.append("report must contain exactly two vehicles")
        return errors
    if {vehicle.get("uav_id") for vehicle in vehicles if isinstance(vehicle, dict)} != {
        "uav1",
        "uav2",
    }:
        errors.append("vehicle identities must be uav1 and uav2")

    identities = [
        vehicle.get("bridge_identity", {}) if isinstance(vehicle, dict) else {}
        for vehicle in vehicles
    ]
    for field in ("copter_id", "sensor_seq_id", "udp_port", "identity_topic"):
        values = [identity.get(field) for identity in identities]
        if any(value is None or value == "" for value in values):
            errors.append(f"missing bridge identity field: {field}")
        if _duplicates(values):
            errors.append(f"duplicate {field}")
    for field in ("raw_lidar_topic", "raw_imu_topic"):
        values = [identity.get(field) for identity in identities]
        if any(not value for value in values):
            errors.append(f"missing bridge identity field: {field}")
        if _duplicates(values):
            errors.append(f"shared {field}")
    for field in ("node", "process_start_marker"):
        values = [identity.get(field) for identity in identities]
        if any(not value for value in values):
            errors.append(f"missing bridge identity field: {field}")
        if _duplicates(values):
            errors.append(f"duplicate bridge {field}")

    for vehicle, identity in zip(vehicles, identities):
        if not isinstance(vehicle, dict):
            errors.append("vehicle report must be an object")
            continue
        uav_id = vehicle.get("uav_id", "unknown")
        namespace = f"/{uav_id}"
        bridge_node = f"{namespace}/rflysim_sensor_bridge"
        adapter_node = f"{namespace}/rflysim_pointcloud_adapter"
        imu_node = f"{namespace}/rflysim_imu_relay"
        if identity.get("node") != bridge_node:
            errors.append(f"{uav_id} bridge node mismatch")

        diagnostics = vehicle.get("adapter_diagnostics")
        if not isinstance(diagnostics, dict):
            errors.append(f"{uav_id} missing adapter diagnostics")
        else:
            if diagnostics.get("status") != "ready" or diagnostics.get("accepted_scans", 0) <= 0:
                errors.append(f"{uav_id} adapter has no accepted scans")
            if diagnostics.get("point_step") != 32:
                errors.append(f"{uav_id} cloud point_step mismatch")
            if tuple(diagnostics.get("fields", ())) != REQUIRED_CLOUD_FIELDS:
                errors.append(f"{uav_id} cloud schema mismatch")
            if not _number(diagnostics.get("time_span_sec")) or diagnostics.get("time_span_sec", 0) <= 0:
                errors.append(f"{uav_id} invalid cloud time span")

        spans = vehicle.get("cloud_time_spans_sec")
        if not isinstance(spans, list) or not spans or not all(
            _number(value) and value > 0 for value in spans
        ):
            errors.append(f"{uav_id} invalid cloud time spans")

        canonical_publishers = {
            identity.get("raw_lidar_topic"): bridge_node,
            identity.get("raw_imu_topic"): bridge_node,
            f"{namespace}/rflysim/lidar": adapter_node,
            f"{namespace}/rflysim/imu": imu_node,
        }
        expected_publishers = vehicle.get("expected_publishers")
        observed_publishers = vehicle.get("publishers")
        if not isinstance(expected_publishers, dict) or not isinstance(observed_publishers, dict):
            errors.append(f"{uav_id} missing publisher maps")
        else:
            for topic, expected_node in canonical_publishers.items():
                if not topic:
                    continue
                if expected_publishers.get(topic) != expected_node:
                    errors.append(f"{uav_id} expected publisher mismatch for {topic}")
                if observed_publishers.get(topic) != [expected_node]:
                    errors.append(f"{uav_id} wrong publishers for {topic}")

        topic_stamps = vehicle.get("topic_stamps")
        if not isinstance(topic_stamps, dict):
            errors.append(f"{uav_id} missing topic timestamps")
        else:
            for topic_name in ("lidar", "imu", "slam_odom", "mavros_feedback"):
                if not _strictly_increasing(topic_stamps.get(topic_name)):
                    errors.append(f"{uav_id} non-monotonic timestamps: {topic_name}")

        stationary = vehicle.get("stationary")
        if not isinstance(stationary, dict):
            errors.append(f"{uav_id} missing stationary observations")
        else:
            observation = stationary.get("observation_sec")
            position = stationary.get("position_delta_m")
            velocity = stationary.get("velocity_max_mps")
            attitude = stationary.get("attitude_delta_rad")
            if not _number(observation) or observation < limits.get("minimum_observation_sec", 5.0):
                errors.append(f"{uav_id} stationary observation window too short")
            if not _number(position) or position > limits.get("maximum_position_delta_m", 0.15):
                errors.append(f"{uav_id} excessive stationary drift")
            if not _number(velocity) or velocity > limits.get("maximum_velocity_mps", 0.1):
                errors.append(f"{uav_id} excessive stationary velocity")
            if not _number(attitude) or attitude > limits.get("maximum_attitude_delta_rad", 0.1):
                errors.append(f"{uav_id} excessive stationary attitude change")

        state = vehicle.get("mavros_state")
        if not isinstance(state, dict) or state.get("armed") is not False:
            errors.append(f"{uav_id} vehicle already armed or arm state unavailable")

    return errors


def _limits_from_config(config):
    configured = config.get("fast_lio", {}).get("readiness", {})
    return {
        name: float(configured.get(name, default)) for name, default in DEFAULT_LIMITS.items()
    }


def _empty_vehicle(bridge):
    uav_id = bridge["uav_id"]
    namespace = f"/{uav_id}"
    bridge_node = f"{namespace}/rflysim_sensor_bridge"
    adapter_node = f"{namespace}/rflysim_pointcloud_adapter"
    imu_node = f"{namespace}/rflysim_imu_relay"
    expected = {
        bridge["raw_lidar_topic"]: bridge_node,
        bridge["raw_imu_topic"]: bridge_node,
        bridge["lidar_topic"]: adapter_node,
        bridge["imu_topic"]: imu_node,
    }
    return {
        "uav_id": uav_id,
        "bridge_identity": {
            "copter_id": bridge["copter_id"],
            "sensor_seq_id": bridge["sensor_seq_id"],
            "udp_port": bridge["udp_port"],
            "identity_topic": bridge["identity_topic"],
            "raw_lidar_topic": bridge["raw_lidar_topic"],
            "raw_imu_topic": bridge["raw_imu_topic"],
            "node": bridge_node,
            "process_start_marker": "not_executed",
        },
        "adapter_diagnostics": {"status": "not_executed", "accepted_scans": 0},
        "publishers": {},
        "expected_publishers": expected,
        "topic_stamps": {name: [] for name in ("lidar", "imu", "slam_odom", "mavros_feedback")},
        "cloud_time_spans_sec": [],
        "stationary": {
            "observation_sec": 0.0,
            "position_delta_m": None,
            "velocity_max_mps": None,
            "attitude_delta_rad": None,
        },
        "mavros_state": {"armed": None, "mode": None},
    }


def build_dry_run_report(config, run_id, simulation_instance_id, created_at):
    bridges = config.get("fast_lio", {}).get("bridges", [])
    if not isinstance(bridges, list) or len(bridges) != 2:
        raise ValueError("Stage 7 config must contain two fast_lio.bridges entries")
    return {
        "backend": "dry-run",
        "ready": False,
        "created_at": float(created_at),
        "run_id": run_id,
        "simulation_instance_id": simulation_instance_id,
        "gates": {gate: "not_executed" for gate in GATE_NAMES},
        "limits": _limits_from_config(config),
        "vehicles": [_empty_vehicle(bridge) for bridge in bridges],
    }


def _stamp(message):
    return float(message.header.stamp.to_sec())


def _cloud_time_span(message):
    field = next((item for item in message.fields if item.name == "t"), None)
    if field is None or message.width * message.height <= 0 or message.point_step <= field.offset + 4:
        return 0.0
    count = message.width * message.height
    first = struct.unpack_from("<I", bytes(message.data), field.offset)[0]
    last = struct.unpack_from(
        "<I", bytes(message.data), (count - 1) * message.point_step + field.offset
    )[0]
    return (last - first) / 1_000_000_000.0 if last >= first else 0.0


def _distance(left, right):
    return math.sqrt(sum((a - b) ** 2 for a, b in zip(left, right)))


def _quaternion_angle(left, right):
    dot = abs(sum(a * b for a, b in zip(left, right)))
    return 2.0 * math.acos(max(-1.0, min(1.0, dot)))


def _publisher_map(rospy):
    code, message, state = rospy.get_master().getSystemState()
    if code != 1:
        raise RuntimeError(f"cannot inspect ROS publisher graph: {message}")
    return {topic: sorted(nodes) for topic, nodes in state[0]}


def _gate_for_error(error):
    if any(word in error for word in ("identity", "copter_id", "sensor_seq_id", "udp_port")):
        return "identity"
    if any(word in error for word in ("schema", "point_step", "cloud time", "accepted scans")):
        return "schema"
    if any(word in error for word in ("timestamp", "fresh", "stale")):
        return "freshness"
    if any(word in error for word in ("publisher", "shared", "bridge node")):
        return "isolation"
    return "stationary_stability"


def collect_live_report(config, run_id, simulation_instance_id, timeout_s):
    import rospy
    from mavros_msgs.msg import State
    from nav_msgs.msg import Odometry
    from sensor_msgs.msg import Imu, PointCloud2
    from std_msgs.msg import String

    if not rospy.core.is_initialized():
        rospy.init_node("stage7_sensor_readiness", anonymous=False)
    bridges = sorted(config.get("fast_lio", {}).get("bridges", []), key=lambda item: item["uav_id"])
    uavs = {item["uav_id"]: item for item in config.get("uavs", [])}
    if len(bridges) != 2 or set(uavs) != {"uav1", "uav2"}:
        raise ValueError("Stage 7 config must contain two matching bridges and UAVs")

    observations = {}
    for bridge in bridges:
        uav_id = bridge["uav_id"]
        diagnostics_topic = bridge.get(
            "diagnostics_topic", f"/{uav_id}/rflysim/adapter_diagnostics"
        )
        identity_message = rospy.wait_for_message(bridge["identity_topic"], String, timeout=timeout_s)
        diagnostics_message = rospy.wait_for_message(diagnostics_topic, String, timeout=timeout_s)
        identity = json.loads(identity_message.data)
        diagnostics = json.loads(diagnostics_message.data)
        observations[uav_id] = {
            "bridge": bridge,
            "uav": uavs[uav_id],
            "identity": identity,
            "diagnostics": diagnostics,
            "stamps": {name: [] for name in ("lidar", "imu", "slam_odom", "mavros_feedback")},
            "cloud_spans": [],
            "positions": [],
            "velocities": [],
            "attitudes": [],
            "states": [],
            "last_cloud": None,
        }

    limits = _limits_from_config(config)
    started = time.monotonic()
    deadline = started + limits["minimum_observation_sec"]
    while time.monotonic() < deadline and not rospy.is_shutdown():
        for uav_id, item in observations.items():
            bridge = item["bridge"]
            uav = item["uav"]
            cloud = rospy.wait_for_message(bridge["lidar_topic"], PointCloud2, timeout=timeout_s)
            imu = rospy.wait_for_message(bridge["imu_topic"], Imu, timeout=timeout_s)
            odom = rospy.wait_for_message(uav["slam_odom_topic"], Odometry, timeout=timeout_s)
            feedback = rospy.wait_for_message(
                uav["mavros_feedback_odom_topic"], Odometry, timeout=timeout_s
            )
            state = rospy.wait_for_message(uav["mavros_state_topic"], State, timeout=timeout_s)
            item["stamps"]["lidar"].append(_stamp(cloud))
            item["stamps"]["imu"].append(_stamp(imu))
            item["stamps"]["slam_odom"].append(_stamp(odom))
            item["stamps"]["mavros_feedback"].append(_stamp(feedback))
            item["cloud_spans"].append(_cloud_time_span(cloud))
            item["last_cloud"] = cloud
            position = odom.pose.pose.position
            velocity = odom.twist.twist.linear
            orientation = odom.pose.pose.orientation
            values = (
                position.x,
                position.y,
                position.z,
                velocity.x,
                velocity.y,
                velocity.z,
                orientation.x,
                orientation.y,
                orientation.z,
                orientation.w,
            )
            if not all(_number(value) for value in values):
                raise ValueError(f"{uav_id} odometry contains non-finite values")
            item["positions"].append((position.x, position.y, position.z))
            item["velocities"].append(math.sqrt(velocity.x ** 2 + velocity.y ** 2 + velocity.z ** 2))
            item["attitudes"].append(
                (orientation.x, orientation.y, orientation.z, orientation.w)
            )
            item["states"].append({"armed": bool(state.armed), "mode": state.mode})

    observation_sec = time.monotonic() - started
    all_publishers = _publisher_map(rospy)
    vehicles = []
    for uav_id, item in observations.items():
        bridge = item["bridge"]
        identity = dict(item["identity"])
        identity["node"] = f"/{uav_id}/rflysim_sensor_bridge"
        diagnostics = dict(item["diagnostics"])
        cloud = item["last_cloud"]
        diagnostics["fields"] = [field.name for field in cloud.fields] if cloud else []
        diagnostics["point_step"] = cloud.point_step if cloud else None
        diagnostics["time_span_sec"] = item["cloud_spans"][-1] if item["cloud_spans"] else None
        namespace = f"/{uav_id}"
        expected = {
            bridge["raw_lidar_topic"]: f"{namespace}/rflysim_sensor_bridge",
            bridge["raw_imu_topic"]: f"{namespace}/rflysim_sensor_bridge",
            bridge["lidar_topic"]: f"{namespace}/rflysim_pointcloud_adapter",
            bridge["imu_topic"]: f"{namespace}/rflysim_imu_relay",
        }
        initial_position = item["positions"][0] if item["positions"] else (math.nan,) * 3
        initial_attitude = item["attitudes"][0] if item["attitudes"] else (math.nan,) * 4
        states = item["states"]
        vehicles.append(
            {
                "uav_id": uav_id,
                "bridge_identity": identity,
                "adapter_diagnostics": diagnostics,
                "publishers": {topic: all_publishers.get(topic, []) for topic in expected},
                "expected_publishers": expected,
                "topic_stamps": item["stamps"],
                "cloud_time_spans_sec": item["cloud_spans"],
                "stationary": {
                    "observation_sec": observation_sec,
                    "position_delta_m": max(
                        (_distance(initial_position, value) for value in item["positions"]),
                        default=math.inf,
                    ),
                    "velocity_max_mps": max(item["velocities"], default=math.inf),
                    "attitude_delta_rad": max(
                        (_quaternion_angle(initial_attitude, value) for value in item["attitudes"]),
                        default=math.inf,
                    ),
                },
                "mavros_state": {
                    "armed": any(state["armed"] for state in states) if states else None,
                    "mode": states[-1]["mode"] if states else None,
                },
            }
        )

    report = {
        "backend": "ros",
        "ready": True,
        "created_at": time.time(),
        "run_id": run_id,
        "simulation_instance_id": simulation_instance_id,
        "gates": {gate: "pass" for gate in GATE_NAMES},
        "limits": limits,
        "vehicles": vehicles,
    }
    errors = validate_report(report, run_id, simulation_instance_id, 30.0, report["created_at"])
    for error in errors:
        report["gates"][_gate_for_error(error)] = "fail"
    report["ready"] = not errors
    report["errors"] = errors
    return report


def _load_json(path):
    return json.loads(path.read_text(encoding="utf-8"))


def _write_json(path, value):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value, indent=2, sort_keys=True) + "\n", encoding="utf-8")


def _print_summary(report, errors):
    gates = report.get("gates", {}) if isinstance(report, dict) else {}
    print(" ".join(f"{gate}={gates.get(gate, 'missing')}" for gate in GATE_NAMES))
    vehicles = report.get("vehicles", []) if isinstance(report, dict) else []
    for vehicle in vehicles:
        state = vehicle.get("mavros_state", {})
        print(f"{vehicle.get('uav_id', 'unknown')}.armed={state.get('armed')}")
    print(f"ready={not errors}")
    for error in errors:
        print(f"[ERROR] {error}", file=sys.stderr)


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--config", type=Path)
    parser.add_argument("--report", required=True, type=Path)
    parser.add_argument("--run-id", required=True)
    parser.add_argument("--simulation-instance-id", required=True)
    parser.add_argument("--backend", choices=("dry-run", "ros"), default="dry-run")
    parser.add_argument("--timeout-s", type=float, default=3.0)
    parser.add_argument("--max-age-sec", type=float, default=30.0)
    parser.add_argument("--validate", action="store_true")
    args = parser.parse_args(argv)

    if args.validate:
        try:
            report = _load_json(args.report)
            errors = validate_report(
                report,
                args.run_id,
                args.simulation_instance_id,
                args.max_age_sec,
                time.time(),
            )
        except Exception as exc:
            print(f"[ERROR] cannot validate readiness report: {exc}", file=sys.stderr)
            return 1
        _print_summary(report, errors)
        return 1 if errors else 0

    if args.config is None:
        print("[ERROR] --config is required when generating a report", file=sys.stderr)
        return 1
    try:
        config = _load_json(args.config)
        if args.backend == "dry-run":
            report = build_dry_run_report(
                config, args.run_id, args.simulation_instance_id, time.time()
            )
        else:
            report = collect_live_report(
                config, args.run_id, args.simulation_instance_id, args.timeout_s
            )
    except Exception as exc:
        try:
            report = build_dry_run_report(
                config, args.run_id, args.simulation_instance_id, time.time()
            )
        except Exception:
            report = {
                "backend": args.backend,
                "ready": False,
                "created_at": time.time(),
                "run_id": args.run_id,
                "simulation_instance_id": args.simulation_instance_id,
                "gates": {gate: "fail" for gate in GATE_NAMES},
                "vehicles": [],
            }
        report["backend"] = args.backend
        report["error"] = str(exc)
        report["ready"] = False
        report["gates"] = {gate: "fail" for gate in GATE_NAMES}
        _write_json(args.report, report)
        print(f"[ERROR] {exc}", file=sys.stderr)
        return 1

    _write_json(args.report, report)
    if args.backend == "dry-run":
        return 0
    errors = validate_report(
        report,
        args.run_id,
        args.simulation_instance_id,
        args.max_age_sec,
        time.time(),
    )
    _print_summary(report, errors)
    return 1 if errors else 0


if __name__ == "__main__":
    raise SystemExit(main())
