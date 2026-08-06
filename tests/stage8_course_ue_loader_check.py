#!/usr/bin/env python3
"""Contract checks for the safe Stage 8 RflySim scene loader."""

from __future__ import annotations

import argparse
import importlib.util
import json
import math
import os
import subprocess
import sys
from pathlib import Path


def load_module(name: str, module_path: Path):
    spec = importlib.util.spec_from_file_location(name, module_path)
    if spec is None or spec.loader is None:
        raise RuntimeError("cannot load module from {}".format(module_path))
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


class FakeUEClient:
    def __init__(self):
        self.map_commands = []
        self.destroyed = []
        self.created = []

    def sendUE4Cmd(self, command, window_id=-1):
        self.map_commands.append((command, window_id))

    def sendUE4Destroy(self, copter_id, window_id=-1):
        self.destroyed.append((copter_id, window_id))

    def sendUE4PosScale(self, **kwargs):
        self.created.append(kwargs)


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--geometry-module", type=Path, required=True)
    parser.add_argument("--loader-module", type=Path, required=True)
    parser.add_argument("--spec", type=Path, required=True)
    args = parser.parse_args()

    geometry = load_module("narrow_course_geometry", args.geometry_module)
    loader = load_module("narrow_course_ue_loader", args.loader_module)
    model = geometry.load_course(args.spec)
    commands = loader.build_ue_commands(model)

    assert len(commands) == len(model.scene_objects) == 34
    assert [command.copter_id for command in commands] == [
        obj.copter_id for obj in model.scene_objects
    ]
    assert len(set(command.copter_id for command in commands)) == len(commands)
    assert all(command.vehicle_type == 1000813 for command in commands)
    assert all(12000 <= command.copter_id <= 12999 for command in commands)

    first_wall = commands[0]
    source_wall = model.wall_boxes[0]
    assert first_wall.position_ned == geometry.enu_to_ned(source_wall.center)
    assert math.isclose(first_wall.yaw_ned, geometry.yaw_enu_to_ned(source_wall.yaw_rad))
    assert first_wall.scale == source_wall.size
    assert first_wall.position_ned.z == 0.0

    client = FakeUEClient()
    original_sleep = loader.time.sleep
    loader.time.sleep = lambda _seconds: None
    try:
        receipt = loader.load_scene(client, model, clear_first=True, window_id=0)
        explicit_client = FakeUEClient()
        explicit_receipt = loader.load_scene(
            explicit_client,
            model,
            clear_first=False,
            window_id=2,
            change_map=True,
        )
        no_collision_client = FakeUEClient()
        no_collision_receipt = loader.load_scene(
            no_collision_client,
            model,
            clear_first=False,
            window_id=0,
            enable_collision=False,
        )
    finally:
        loader.time.sleep = original_sleep
    assert client.map_commands == [("RflyChangeViewKeyCmd P", 0)], (
        "default live load must enable the RflySim collision engine"
    )
    assert client.destroyed == [(value, 0) for value in range(12000, 13000)]
    assert len(client.created) == len(commands) * 3
    for index, command in enumerate(commands):
        repeated = client.created[index * 3 : index * 3 + 3]
        assert len(repeated) == 3 and repeated[0] == repeated[1] == repeated[2]
        call = repeated[0]
        assert call["copterID"] == command.copter_id
        assert call["vehicleType"] == 1000813
        assert call["MotorRPMSMean"] == 0
        assert call["PosE"] == list(command.position_ned)
        assert call["AngEuler"] == [0.0, 0.0, command.yaw_ned]
        assert call["Scale"] == list(command.scale)
        assert call["windowID"] == 0
    assert receipt == {
        "base_map": "SLAMScene",
        "change_map": False,
        "clear_first": True,
        "id_range": [12000, 12999],
        "mode": "live",
        "object_count": 34,
        "collision_enabled": True,
        "spec_sha256": model.spec_sha256,
        "window_id": 0,
    }
    assert explicit_client.map_commands == [
        ("RflyChangeMapbyName SLAMScene", 2),
        ("RflyChangeViewKeyCmd P", 2),
    ]
    assert explicit_client.destroyed == []
    assert len(explicit_client.created) == len(commands) * 3
    assert explicit_receipt["change_map"] is True
    assert explicit_receipt["collision_enabled"] is True
    assert no_collision_client.map_commands == []
    assert no_collision_receipt["collision_enabled"] is False

    dry_env = dict(os.environ)
    dry_env["RFLYSIM_ROOT"] = str(args.spec.parent / "does-not-exist")
    dry_run = subprocess.run(
        [
            sys.executable,
            str(args.loader_module),
            "--spec",
            str(args.spec),
            "--dry-run",
            "--window-id",
            "2",
        ],
        check=False,
        capture_output=True,
        text=True,
        env=dry_env,
    )
    assert dry_run.returncode == 0, dry_run.stderr
    dry_receipt = json.loads(dry_run.stdout)
    assert dry_receipt["mode"] == "dry-run"
    assert dry_receipt["change_map"] is False
    assert dry_receipt["window_id"] == 2
    assert dry_receipt["object_count"] == 34
    assert dry_receipt["collision_enabled"] is True
    assert dry_receipt["commands"][0]["position_ned"] == list(commands[0].position_ned)

    explicit_dry_run = subprocess.run(
        [
            sys.executable,
            str(args.loader_module),
            "--spec",
            str(args.spec),
            "--dry-run",
            "--change-map",
        ],
        check=False,
        capture_output=True,
        text=True,
        env=dry_env,
    )
    assert explicit_dry_run.returncode == 0, explicit_dry_run.stderr
    assert json.loads(explicit_dry_run.stdout)["change_map"] is True

    print("stage8 course UE loader: PASS")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
