#!/usr/bin/env python3
"""Validate the C++ mission package boundary and byte-preserving migration."""

from __future__ import annotations

import argparse
import hashlib
import sys
from pathlib import Path


OLD_INCLUDE = b'#include "ego_setpoint_bridge.hpp"'
NEW_INCLUDE = b'#include "future_aircraft_mission/ego_setpoint_bridge.hpp"'
MIGRATED_FILES = (
    ("include/ego_setpoint_bridge.hpp", "include/future_aircraft_mission/ego_setpoint_bridge.hpp"),
    ("src/ego_setpoint_bridge.cpp", "src/ego_setpoint_bridge.cpp"),
    ("src/ego_setpoint_bridge_node.cpp", "src/ego_setpoint_bridge_node.cpp"),
)


def sha256(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def check_migration_hashes(project_root: Path, errors: list[str]) -> None:
    baseline = project_root / "future_aircraft_ws/src/multi_uav_mission"
    mission = project_root / "future_aircraft_ws/src/future_aircraft_mission"
    for source_relative, destination_relative in MIGRATED_FILES:
        source = baseline / source_relative
        destination = mission / destination_relative
        if not source.is_file() or not destination.is_file():
            continue
        source_data = source.read_bytes()
        destination_data = destination.read_bytes()
        canonical_destination = destination_data.replace(NEW_INCLUDE, OLD_INCLUDE, 1)
        if sha256(source_data) != sha256(canonical_destination):
            errors.append(
                "migration changed bytes beyond the permitted include normalization: "
                f"{source_relative}"
            )


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--project-root", required=True, type=Path)
    args = parser.parse_args()
    root = args.project_root.resolve()

    mission_root = root / "future_aircraft_ws/src/future_aircraft_mission"
    mission_package_path = mission_root / "package.xml"
    mission_cmake_path = mission_root / "CMakeLists.txt"
    baseline_cmake_path = root / "future_aircraft_ws/src/multi_uav_mission/CMakeLists.txt"

    errors: list[str] = []
    if not mission_package_path.is_file():
        errors.append("future_aircraft_mission/package.xml is missing")
    if not mission_cmake_path.is_file():
        errors.append("future_aircraft_mission/CMakeLists.txt is missing")

    mission_cmake = mission_cmake_path.read_text(encoding="utf-8") if mission_cmake_path.is_file() else ""
    mission_package = mission_package_path.read_text(encoding="utf-8") if mission_package_path.is_file() else ""
    baseline_cmake = baseline_cmake_path.read_text(encoding="utf-8")

    if "add_library(future_aircraft_mission" not in mission_cmake:
        errors.append("future_aircraft_mission library target is missing")
    if "add_executable(ego_setpoint_bridge_node" not in mission_cmake:
        errors.append("ego_setpoint_bridge_node executable target is missing")
    if "src/ego_setpoint_bridge.cpp" in baseline_cmake:
        errors.append("multi_uav_mission still builds ego_setpoint_bridge.cpp")
    if "<depend>quadrotor_msgs</depend>" not in mission_package:
        errors.append("future_aircraft_mission must depend on quadrotor_msgs")
    if "<depend>mavros_msgs</depend>" not in mission_package:
        errors.append("future_aircraft_mission must depend on mavros_msgs")

    check_migration_hashes(root, errors)

    if errors:
        for error in errors:
            print(f"[FAIL] {error}", file=sys.stderr)
        return 1
    print("[PASS] future_aircraft_mission package boundary is valid")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
