#!/usr/bin/env python3
"""Load the predicted narrow course as a safe RflySim dynamic layer."""

from __future__ import annotations

import argparse
import json
import os
import sys
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Dict, List

from narrow_course_geometry import CourseModel, Vec3, enu_to_ned, load_course, yaw_enu_to_ned


@dataclass(frozen=True)
class UECommand:
    copter_id: int
    vehicle_type: int
    position_ned: Vec3
    yaw_ned: float
    scale: Vec3


def build_ue_commands(model: CourseModel) -> List[UECommand]:
    asset = model.raw["asset"]
    vehicle_type = int(asset["vehicle_type"])
    native = Vec3(*(float(value) for value in asset["native_size"]))
    if min(native) <= 0.0:
        raise ValueError("asset native_size must be positive")
    return [
        UECommand(
            copter_id=obj.copter_id,
            vehicle_type=vehicle_type,
            position_ned=enu_to_ned(obj.center),
            yaw_ned=yaw_enu_to_ned(obj.yaw_rad),
            scale=Vec3(obj.size.x / native.x, obj.size.y / native.y, obj.size.z / native.z),
        )
        for obj in model.scene_objects
    ]


def load_scene(
    client,
    model: CourseModel,
    clear_first: bool,
    window_id: int,
    change_map: bool = False,
    enable_collision: bool = True,
) -> Dict[str, object]:
    commands = build_ue_commands(model)
    if change_map:
        client.sendUE4Cmd("RflyChangeMapbyName {}".format(model.base_map), window_id)
        time.sleep(3.0)
    if clear_first:
        for copter_id in range(model.owned_id_range[0], model.owned_id_range[1] + 1):
            client.sendUE4Destroy(copter_id, window_id)
    for command in commands:
        kwargs = {
            "copterID": command.copter_id,
            "vehicleType": command.vehicle_type,
            "MotorRPMSMean": 0,
            "PosE": list(command.position_ned),
            "AngEuler": [0.0, 0.0, command.yaw_ned],
            "Scale": list(command.scale),
            "windowID": window_id,
        }
        for _attempt in range(3):
            client.sendUE4PosScale(**kwargs)
            time.sleep(0.02)
    if enable_collision:
        client.sendUE4Cmd("RflyChangeViewKeyCmd P", window_id)
    return {
        "base_map": model.base_map,
        "change_map": change_map,
        "clear_first": clear_first,
        "collision_enabled": enable_collision,
        "id_range": list(model.owned_id_range),
        "mode": "live",
        "object_count": len(commands),
        "spec_sha256": model.spec_sha256,
        "window_id": window_id,
    }


def _command_dict(command: UECommand) -> Dict[str, object]:
    return {
        "copter_id": command.copter_id,
        "position_ned": list(command.position_ned),
        "scale": list(command.scale),
        "vehicle_type": command.vehicle_type,
        "yaw_ned": command.yaw_ned,
    }


def _verify_report(path: Path, model: CourseModel) -> None:
    try:
        report = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise ValueError("cannot read validation report {}: {}".format(path, exc)) from exc
    if report.get("spec_sha256") != model.spec_sha256:
        raise ValueError("validation report checksum does not match the course spec")


def _create_client(rflysim_root: Path):
    api_dir = rflysim_root / "RflySimAPIs" / "RflySimSDK" / "ue"
    if not api_dir.is_dir():
        raise RuntimeError("RflySim UE API directory does not exist: {}".format(api_dir))
    sys.path.insert(0, str(api_dir))
    import UE4CtrlAPI  # pylint: disable=import-error,import-outside-toplevel

    return UE4CtrlAPI.UE4CtrlAPI()


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--spec", type=Path, required=True)
    parser.add_argument("--validation-report", type=Path)
    parser.add_argument("--window-id", type=int, default=-1)
    parser.add_argument("--change-map", action="store_true")
    parser.add_argument("--no-clear", action="store_true")
    parser.add_argument("--no-enable-collision", action="store_true")
    parser.add_argument("--dry-run", action="store_true")
    parser.add_argument(
        "--rflysim-root",
        type=Path,
        default=Path(os.environ.get("RFLYSIM_ROOT", r"D:\PX4PSP")),
    )
    args = parser.parse_args()

    model = load_course(args.spec)
    if args.validation_report is not None:
        _verify_report(args.validation_report, model)
    commands = build_ue_commands(model)
    if args.dry_run:
        receipt = {
            "base_map": model.base_map,
            "change_map": args.change_map,
            "clear_first": not args.no_clear,
            "collision_enabled": not args.no_enable_collision,
            "commands": [_command_dict(command) for command in commands],
            "id_range": list(model.owned_id_range),
            "mode": "dry-run",
            "object_count": len(commands),
            "spec_sha256": model.spec_sha256,
            "window_id": args.window_id,
        }
    else:
        receipt = load_scene(
            _create_client(args.rflysim_root),
            model,
            clear_first=not args.no_clear,
            window_id=args.window_id,
            change_map=args.change_map,
            enable_collision=not args.no_enable_collision,
        )
    print(json.dumps(receipt, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
