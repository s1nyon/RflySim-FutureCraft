#!/usr/bin/env python3
"""Derive the RflySim stage-2 NED spawn environment from the V2 ENU spec."""

from __future__ import annotations

import argparse
import json
import math
from pathlib import Path
from typing import Any, Dict


def _number(value: Any, label: str) -> float:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise ValueError("{} must be a finite number".format(label))
    result = float(value)
    if not math.isfinite(result):
        raise ValueError("{} must be finite".format(label))
    return result


def _fmt(value: float) -> str:
    result = "{:.12g}".format(value)
    return "0" if result == "-0" else result


def spawn_environment(spec: Dict[str, Any]) -> Dict[str, str]:
    if spec.get("coordinate_frame") != "ENU":
        raise ValueError("competition course spawn source must be ENU")
    spawns = spec.get("spawns", {})
    yaws = spec.get("spawn_yaw_deg", {})
    if set(spawns) != {"uav1", "uav2"} or set(yaws) != {"uav1", "uav2"}:
        raise ValueError("spawns and spawn_yaw_deg must contain uav1 and uav2")
    ordered = []
    ordered_yaw = []
    for name in ("uav1", "uav2"):
        position = spawns[name]
        if not isinstance(position, list) or len(position) != 3:
            raise ValueError("{} spawn must contain three ENU values".format(name))
        ordered.append([_number(item, "{} spawn".format(name)) for item in position])
        ordered_yaw.append(_number(yaws[name], "{} yaw".format(name)))
    return {
        "STAGE2_POS_X_STR": ",".join(_fmt(position[1]) for position in ordered),
        "STAGE2_POS_Y_STR": ",".join(_fmt(position[0]) for position in ordered),
        "STAGE2_YAW_STR": ",".join(_fmt(90.0 - yaw) for yaw in ordered_yaw),
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--spec", type=Path, required=True)
    args = parser.parse_args()
    spec = json.loads(args.spec.read_text(encoding="utf-8"))
    environment = spawn_environment(spec)
    for key in ("STAGE2_POS_X_STR", "STAGE2_POS_Y_STR", "STAGE2_YAW_STR"):
        print("set {}={}".format(key, environment[key]))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
