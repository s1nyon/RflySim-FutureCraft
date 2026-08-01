#!/usr/bin/env python3
"""Contract check for independent Stage 7 RflySim sensor bridges."""

from __future__ import annotations

import argparse
import json
from pathlib import Path


def load_json(path: Path):
    with path.open(encoding="utf-8") as stream:
        return json.load(stream)


def validate(stage7, sensor_configs):
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
        sensor = sensor_configs[bridge["uav_id"]]["VisionSensors"][0]
        assert sensor["TargetCopter"] == bridge["copter_id"]
        assert sensor["SeqID"] == bridge["sensor_seq_id"]
        assert sensor["SendProtocol"][5] == bridge["udp_port"]


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
    validate(stage7, sensor_configs)
    for bridge in stage7["fast_lio"]["bridges"]:
        print(
            f"{bridge['uav_id']}: copter={bridge['copter_id']} "
            f"sensor={bridge['sensor_seq_id']} udp={bridge['udp_port']} "
            f"identity={bridge['identity_topic']}"
        )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
