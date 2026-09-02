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
        assert len(sensors) >= 4, "VisionSensors"
        validate_sdk_loadable(sensors)
        assert len({sensor["SeqID"] for sensor in sensors}) == len(sensors), "unique SeqID"
        assert len({sensor["SendProtocol"][5] for sensor in sensors}) == len(sensors), "unique UDP port"
        lidar_sensors = [sensor for sensor in sensors if sensor["TypeID"] == 23]
        assert len(lidar_sensors) == 1, "lidar count"
        sensor = lidar_sensors[0]
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
        rgb = [sensor for sensor in sensors if sensor["TypeID"] == 1 and sensor["SensorPosXYZ"] == [0.1, 0.04, 0.0]]
        assert len(rgb) == 1, "D435i RGB"
        assert rgb[0]["DataWidth"] == 640 and rgb[0]["DataHeight"] == 480, "D435i RGB resolution"
        depth = [sensor for sensor in sensors if sensor["TypeID"] == 2]
        assert len(depth) == 1, "D435i depth"
        assert depth[0]["SensorPosXYZ"] == [0.1, 0.04, 0.0], "D435i depth pose"
        assert depth[0]["otherParams"][:3] == [0.3, 12, 0.001], "D435i depth params"
        bottom = [
            sensor
            for sensor in sensors
            if sensor["TypeID"] == 1
            and sensor["SensorPosXYZ"] == [0, 0, 0.1]
            and sensor["SensorAngEular"] == [0, -90, 0]
        ]
        assert len(bottom) == 1, "downward camera"
        for sensor in sensors:
            assert sensor["TargetCopter"] == bridge["copter_id"], "sensor copter binding"


def validate_sdk_loadable(sensors):
    """Mirror VisionCaptureApi.jsonLoad format rules for every sensor entry."""
    for sensor in sensors:
        assert len(sensor["SendProtocol"]) == 8, "SendProtocol must have 8 entries"
        assert len(sensor["SensorPosXYZ"]) == 3, "SensorPosXYZ must have 3 entries"
        assert len(sensor["SensorAngEular"]) == 3, "SensorAngEular must have 3 entries"
        params = sensor["otherParams"]
        assert len(params) in (8, 16), "otherParams must have 8 or 16 entries"
        if len(params) == 16:
            assert "EularOrQuat" in sensor, "16-dim otherParams requires EularOrQuat"
            assert len(sensor["SensorAngQuat"]) == 4, "EularOrQuat requires SensorAngQuat[4]"
        else:
            assert "EularOrQuat" not in sensor, "8-dim otherParams must not set EularOrQuat"


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
        lidar_index = next(
            index
            for index, sensor in enumerate(invalid_sensors["uav1"]["VisionSensors"])
            if sensor["TypeID"] == 23
        )
        invalid_sensors["uav1"]["VisionSensors"][lidar_index][field] = incorrect_value
        assert_rejected(
            f"incorrect {field}",
            lambda: validate(stage7, invalid_sensors, sensor_paths),
        )

    missing_depth = deepcopy(sensor_configs)
    missing_depth["uav1"]["VisionSensors"] = [
        sensor for sensor in missing_depth["uav1"]["VisionSensors"] if sensor["TypeID"] != 2
    ]
    assert_rejected(
        "missing D435i depth",
        lambda: validate(stage7, missing_depth, sensor_paths),
    )

    wrong_depth_pose = deepcopy(sensor_configs)
    wrong_depth_pose["uav1"]["VisionSensors"] = [
        {**sensor, "SensorPosXYZ": [0, 0, 0.1]} if sensor["TypeID"] == 2 else sensor
        for sensor in wrong_depth_pose["uav1"]["VisionSensors"]
    ]
    assert_rejected(
        "D435i depth pose mismatch",
        lambda: validate(stage7, wrong_depth_pose, sensor_paths),
    )

    missing_new_protocol_keys = deepcopy(sensor_configs)
    missing_new_protocol_keys["uav1"]["VisionSensors"] = [
        {
            key: value
            for key, value in sensor.items()
            if key not in ("EularOrQuat", "SensorAngQuat")
        }
        if len(sensor.get("otherParams", [])) == 16
        else sensor
        for sensor in missing_new_protocol_keys["uav1"]["VisionSensors"]
    ]
    assert_rejected(
        "16-dim otherParams without EularOrQuat/SensorAngQuat",
        lambda: validate(stage7, missing_new_protocol_keys, sensor_paths),
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
