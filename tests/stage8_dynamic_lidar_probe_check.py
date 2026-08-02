#!/usr/bin/env python3
"""Contract checks for the ChallengeMap dynamic-wall LiDAR probe."""

from __future__ import annotations

import argparse
import importlib.util
import json
import subprocess
import sys
from pathlib import Path


def load_module(module_path: Path):
    spec = importlib.util.spec_from_file_location("stage8_dynamic_lidar_probe", module_path)
    if spec is None or spec.loader is None:
        raise RuntimeError(f"cannot load module from {module_path}")
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


class FakeUEClient:
    def __init__(self):
        self.created = []
        self.destroyed = []

    def sendUE4PosScale(self, **kwargs):
        self.created.append(kwargs)

    def sendUE4Destroy(self, copter_id, window_id=-1):
        self.destroyed.append((copter_id, window_id))


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--module", type=Path, required=True)
    args = parser.parse_args()
    module = load_module(args.module)

    wall = module.build_probe_wall(
        spawn_ned=(0.5, 1.5, 0.0),
        yaw_deg=0.0,
        distance_m=1.5,
    )
    assert wall.object_id == 12999
    assert wall.vehicle_type == 1000813
    assert wall.position_ned == (2.0, 1.5, 0.0)
    assert wall.yaw_ned == 0.0
    assert wall.scale == (0.2, 4.0, 2.5)

    client = FakeUEClient()
    module.place_probe_wall(client, wall, window_id=0, repeat=3, delay_s=0.0)
    assert len(client.created) == 3
    assert client.created[0] == client.created[1] == client.created[2]
    assert client.created[0] == {
        "copterID": 12999,
        "vehicleType": 1000813,
        "MotorRPMSMean": 0,
        "PosE": [2.0, 1.5, 0.0],
        "AngEuler": [0.0, 0.0, 0.0],
        "Scale": [0.2, 4.0, 2.5],
        "windowID": 0,
    }
    module.remove_probe_wall(client, wall, window_id=0, repeat=3, delay_s=0.0)
    assert client.destroyed == [(12999, 0)] * 3

    points = [
        (1.49, 0.0, 0.0),
        (1.55, 1.49, -1.9),
        (1.50, 1.51, 0.0),
        (1.71, 0.0, 0.0),
        (1.40, 0.0, 2.01),
    ]
    assert module.count_wall_roi(points, distance_m=1.5) == 2

    visible = module.analyze_probe(
        before_counts=[4, 5, 5, 6, 5],
        wall_counts=[180, 190, 200, 195, 205],
        after_counts=[5, 6, 4, 5, 5],
        minimum_added_points=100,
    )
    assert visible["dynamic_wall_visible"] is True
    assert visible["added_points"] == 190.0
    assert visible["removed_points"] == 190.0

    invisible = module.analyze_probe(
        before_counts=[10, 11, 10],
        wall_counts=[12, 10, 11],
        after_counts=[10, 9, 11],
        minimum_added_points=100,
    )
    assert invisible["dynamic_wall_visible"] is False

    dry_run = subprocess.run(
        [
            sys.executable,
            str(args.module),
            "wall",
            "--action",
            "create",
            "--spawn-ned-x",
            "29.3",
            "--spawn-ned-y",
            "0",
            "--dry-run",
        ],
        check=False,
        capture_output=True,
        text=True,
    )
    assert dry_run.returncode == 0, dry_run.stderr
    receipt = json.loads(dry_run.stdout)
    assert receipt["action"] == "create"
    assert receipt["dry_run"] is True
    assert receipt["map_change"] is False
    assert receipt["arming_request"] is False
    assert receipt["wall"]["object_id"] == 12999
    assert receipt["wall"]["position_ned"] == [30.8, 0.0, 0.0]

    print("stage8 dynamic LiDAR probe: PASS")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
