#!/usr/bin/env python3
"""Contract check for independent Stage 7 RflySim sensor bridges."""

from __future__ import annotations

import argparse
from copy import deepcopy
import json
from pathlib import Path


def load_json(path: Path):
    with path.open(encoding="utf-8") as stream:
        return json.load(stream)


def validate(stage7, sensor_configs, sensor_paths):
    bridges = stage7["fast_lio"]["bridges"]
    assert len(bridges) == 2
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
        assert len({bridge[field] for bridge in bridges}) == 2, field
    for bridge in bridges:
        uav_id = bridge["uav_id"]
        assert Path(bridge["config"]).resolve() == sensor_paths[uav_id].resolve(), "config"
        sensors = sensor_configs[uav_id]["VisionSensors"]
        assert len(sensors) == 1, "VisionSensors"
        sensor = sensors[0]
        assert sensor["TypeID"] == 23, "TypeID"
        assert sensor["DataWidth"] == 64, "DataWidth"
        assert sensor["DataHeight"] == 272, "DataHeight"
        assert sensor["DataCheckFreq"] == 10, "DataCheckFreq"
        assert sensor["SensorPosXYZ"] == [0, 0, -0.1], "SensorPosXYZ"
        assert sensor["SensorAngEular"] == [0, 0, 0], "SensorAngEular"
        assert bridge["scan_period_s"] == 0.1, "scan_period_s"
        assert sensor["DataCheckFreq"] * bridge["scan_period_s"] == 1, "scan period"
        assert sensor["TargetCopter"] == bridge["copter_id"]
        assert sensor["SeqID"] == bridge["sensor_seq_id"]
        assert sensor["SendProtocol"][5] == bridge["udp_port"]


def assert_rejected(label, callback):
    try:
        callback()
    except AssertionError:
        return
    raise AssertionError(f"{label} must be rejected")


def run_regression_cases(stage7, sensor_configs, sensor_paths):
    shared_config = deepcopy(stage7)
    shared_config["fast_lio"]["bridges"][1]["config"] = shared_config["fast_lio"]["bridges"][0]["config"]
    assert_rejected(
        "shared config reference",
        lambda: validate(shared_config, sensor_configs, sensor_paths),
    )

    for field, incorrect_value in (
        ("TypeID", 22),
        ("DataWidth", 63),
        ("DataHeight", 271),
        ("DataCheckFreq", 9),
        ("SensorPosXYZ", [0, 0, 0]),
        ("SensorAngEular", [1, 0, 0]),
    ):
        invalid_sensors = deepcopy(sensor_configs)
        invalid_sensors["uav1"]["VisionSensors"][0][field] = incorrect_value
        assert_rejected(
            f"incorrect {field}",
            lambda: validate(stage7, invalid_sensors, sensor_paths),
        )

    invalid_period = deepcopy(stage7)
    invalid_period["fast_lio"]["bridges"][0]["scan_period_s"] = 0.2
    assert_rejected(
        "incorrect scan period",
        lambda: validate(invalid_period, sensor_configs, sensor_paths),
    )


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--config", required=True, type=Path)
    parser.add_argument("--uav1-sensor", required=True, type=Path)
    parser.add_argument("--uav2-sensor", required=True, type=Path)
    args = parser.parse_args()

    stage7 = load_json(args.config)
    sensor_configs = {
        "uav1": load_json(args.uav1_sensor),
        "uav2": load_json(args.uav2_sensor),
    }
    sensor_paths = {
        "uav1": args.uav1_sensor,
        "uav2": args.uav2_sensor,
    }
    validate(stage7, sensor_configs, sensor_paths)
    run_regression_cases(stage7, sensor_configs, sensor_paths)
    for bridge in stage7["fast_lio"]["bridges"]:
        print(
            f"{bridge['uav_id']}: copter={bridge['copter_id']} "
            f"sensor={bridge['sensor_seq_id']} udp={bridge['udp_port']} "
            f"identity={bridge['identity_topic']}"
        )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
