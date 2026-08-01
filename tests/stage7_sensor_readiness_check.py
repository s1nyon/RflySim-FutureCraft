#!/usr/bin/env python3
"""Fail-closed checks for Stage 7 dual-sensor readiness reports."""

from __future__ import annotations

import argparse
from copy import deepcopy
import importlib.util
from pathlib import Path
import sys


REQUIRED_FIELDS = [
    "x",
    "y",
    "z",
    "intensity",
    "t",
    "reflectivity",
    "ring",
    "ambient",
    "range",
]


def load_module(module_path: Path, module_name: str):
    spec = importlib.util.spec_from_file_location(module_name, module_path)
    if spec is None or spec.loader is None:
        raise RuntimeError(f"cannot load module from {module_path}")
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


def vehicle(uav_id, copter_id, seq_id, port):
    namespace = f"/{uav_id}"
    bridge_node = f"{namespace}/rflysim_sensor_bridge"
    adapter_node = f"{namespace}/rflysim_pointcloud_adapter"
    imu_node = f"{namespace}/rflysim_imu_relay"
    raw_lidar = f"/rflysim/sensor{seq_id}/mid360_lidar"
    raw_imu = f"{namespace}/rflysim/imu_raw"
    lidar = f"{namespace}/rflysim/lidar"
    imu = f"{namespace}/rflysim/imu"
    return {
        "uav_id": uav_id,
        "bridge_identity": {
            "copter_id": copter_id,
            "sensor_seq_id": seq_id,
            "udp_port": port,
            "identity_topic": f"{namespace}/rflysim/sensor_identity",
            "raw_lidar_topic": raw_lidar,
            "raw_imu_topic": raw_imu,
            "node": bridge_node,
            "process_start_marker": f"run-1:{uav_id}:bridge",
        },
        "adapter_diagnostics": {
            "status": "ready",
            "accepted_scans": 20,
            "accepted_points": 17408,
            "fields": REQUIRED_FIELDS,
            "point_step": 32,
            "time_span_sec": 0.1,
        },
        "publishers": {
            raw_lidar: [bridge_node],
            raw_imu: [bridge_node],
            lidar: [adapter_node],
            imu: [imu_node],
        },
        "expected_publishers": {
            raw_lidar: bridge_node,
            raw_imu: bridge_node,
            lidar: adapter_node,
            imu: imu_node,
        },
        "topic_stamps": {
            "lidar": [100.0, 100.1, 100.2],
            "imu": [100.0, 100.005, 100.01],
            "slam_odom": [100.0, 100.05, 100.1],
            "mavros_feedback": [100.0, 100.05, 100.1],
        },
        "cloud_time_spans_sec": [0.1, 0.1, 0.1],
        "stationary": {
            "observation_sec": 10.0,
            "position_delta_m": 0.03,
            "velocity_max_mps": 0.04,
            "attitude_delta_rad": 0.02,
        },
        "mavros_state": {"armed": False, "mode": "MANUAL"},
    }


def valid_report():
    return {
        "backend": "ros",
        "ready": True,
        "created_at": 100.0,
        "run_id": "run-1",
        "simulation_instance_id": "sim-1",
        "gates": {
            "identity": "pass",
            "schema": "pass",
            "freshness": "pass",
            "isolation": "pass",
            "stationary_stability": "pass",
        },
        "limits": {
            "minimum_observation_sec": 5.0,
            "maximum_position_delta_m": 0.15,
            "maximum_velocity_mps": 0.1,
            "maximum_attitude_delta_rad": 0.1,
        },
        "vehicles": [
            vehicle("uav1", 1, 0, 9999),
            vehicle("uav2", 2, 10, 10009),
        ],
    }


def assert_has_error(module, report, fragment, **overrides):
    errors = module.validate_report(
        report,
        overrides.get("run_id", "run-1"),
        overrides.get("instance_id", "sim-1"),
        overrides.get("max_age_sec", 30.0),
        overrides.get("now", 110.0),
    )
    assert any(fragment in error for error in errors), errors


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--module", type=Path, required=True)
    parser.add_argument("--probe-module", type=Path)
    args = parser.parse_args()
    module = load_module(args.module, "stage7_sensor_readiness")

    report = valid_report()
    assert module.validate_report(report, "run-1", "sim-1", 30.0, 110.0) == []

    dry_config = {
        "fast_lio": {
            "bridges": [
                {
                    "uav_id": "uav1",
                    "copter_id": 1,
                    "sensor_seq_id": 0,
                    "udp_port": 9999,
                    "identity_topic": "/uav1/rflysim/sensor_identity",
                    "raw_lidar_topic": "/rflysim/sensor0/mid360_lidar",
                    "raw_imu_topic": "/uav1/rflysim/imu_raw",
                    "lidar_topic": "/uav1/rflysim/lidar",
                    "imu_topic": "/uav1/rflysim/imu",
                },
                {
                    "uav_id": "uav2",
                    "copter_id": 2,
                    "sensor_seq_id": 10,
                    "udp_port": 10009,
                    "identity_topic": "/uav2/rflysim/sensor_identity",
                    "raw_lidar_topic": "/rflysim/sensor10/mid360_lidar",
                    "raw_imu_topic": "/uav2/rflysim/imu_raw",
                    "lidar_topic": "/uav2/rflysim/lidar",
                    "imu_topic": "/uav2/rflysim/imu",
                },
            ]
        }
    }
    generated_dry_run = module.build_dry_run_report(dry_config, "run-1", "sim-1", 100.0)
    assert generated_dry_run["backend"] == "dry-run"
    assert generated_dry_run["ready"] is False
    assert len(generated_dry_run["vehicles"]) == 2
    assert set(generated_dry_run["gates"].values()) == {"not_executed"}
    assert_has_error(module, generated_dry_run, "live evidence not executed")

    if args.probe_module:
        probe = load_module(args.probe_module, "stage7_topic_probe")
        accepted = probe.evaluate_saved_readiness(report, "run-1", "sim-1", 30.0, 110.0)
        assert accepted["ready"] is True, accepted
        assert accepted["status"] == "readiness_accepted", accepted
        rejected = probe.evaluate_saved_readiness(
            generated_dry_run, "run-1", "sim-1", 30.0, 110.0
        )
        assert rejected["ready"] is False, rejected
        assert "live evidence not executed" in rejected["detail"], rejected

    assert_has_error(module, report, "stale report", max_age_sec=5.0)
    assert_has_error(module, report, "run id mismatch", run_id="run-2")
    assert_has_error(module, report, "simulation instance mismatch", instance_id="sim-2")

    dry_run = deepcopy(report)
    dry_run["backend"] = "dry-run"
    dry_run["ready"] = False
    dry_run["gates"] = {name: "not_executed" for name in report["gates"]}
    assert_has_error(module, dry_run, "live evidence not executed")

    armed = deepcopy(report)
    armed["vehicles"][0]["mavros_state"]["armed"] = True
    assert_has_error(module, armed, "vehicle already armed")

    duplicate_cases = (
        ("copter_id", "duplicate copter_id"),
        ("sensor_seq_id", "duplicate sensor_seq_id"),
        ("udp_port", "duplicate udp_port"),
        ("identity_topic", "duplicate identity_topic"),
    )
    for field, message in duplicate_cases:
        duplicate = deepcopy(report)
        duplicate["vehicles"][1]["bridge_identity"][field] = duplicate["vehicles"][0][
            "bridge_identity"
        ][field]
        assert_has_error(module, duplicate, message)

    shared_lidar = deepcopy(report)
    shared_lidar["vehicles"][1]["bridge_identity"]["raw_lidar_topic"] = shared_lidar[
        "vehicles"
    ][0]["bridge_identity"]["raw_lidar_topic"]
    assert_has_error(module, shared_lidar, "shared raw_lidar_topic")

    shared_imu = deepcopy(report)
    shared_imu["vehicles"][1]["bridge_identity"]["raw_imu_topic"] = shared_imu["vehicles"][0][
        "bridge_identity"
    ]["raw_imu_topic"]
    assert_has_error(module, shared_imu, "shared raw_imu_topic")

    wrong_publisher = deepcopy(report)
    lidar_topic = "/uav1/rflysim/lidar"
    wrong_publisher["vehicles"][0]["publishers"][lidar_topic] = ["/unexpected_node"]
    assert_has_error(module, wrong_publisher, "wrong publishers")

    regressed_stamp = deepcopy(report)
    regressed_stamp["vehicles"][0]["topic_stamps"]["imu"] = [100.0, 99.0, 101.0]
    assert_has_error(module, regressed_stamp, "non-monotonic timestamps")

    excessive_drift = deepcopy(report)
    excessive_drift["vehicles"][1]["stationary"]["position_delta_m"] = 0.2
    assert_has_error(module, excessive_drift, "excessive stationary drift")

    print("stage7 sensor readiness: PASS")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
