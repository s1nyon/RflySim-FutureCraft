#!/usr/bin/env python3
"""Validate VS Code build and IntelliSense metadata for both workspace roots."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path


ROOT_BUILD_SCRIPT = "${workspaceFolder}/scripts/wsl/build_future_aircraft_ws.sh"
ROS_BUILD_SCRIPT = "${workspaceFolder}/../scripts/wsl/build_future_aircraft_ws.sh"
ROOT_COMPILE_COMMANDS = "${workspaceFolder}/future_aircraft_ws/build/compile_commands.json"
ROS_COMPILE_COMMANDS = "${workspaceFolder}/build/compile_commands.json"
OLD_EGO_PATH = "external/ego-planner-swarm"
NEW_EGO_PATH = "third_party/ego-planner-swarm"


def load_json(path: Path, errors: list[str]) -> dict:
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except OSError as exc:
        errors.append(f"cannot read {path}: {exc}")
    except json.JSONDecodeError as exc:
        errors.append(f"invalid JSON in {path}: {exc}")
    return {}


def build_task(tasks_json: dict, path: Path, errors: list[str]) -> dict:
    tasks = tasks_json.get("tasks")
    if not isinstance(tasks, list):
        errors.append(f"{path} must contain a tasks list")
        return {}
    matches = [task for task in tasks if task.get("label") == "build: future_aircraft_ws"]
    if len(matches) != 1:
        errors.append(
            f"{path} must contain exactly one 'build: future_aircraft_ws' task; found {len(matches)}"
        )
        return {}
    return matches[0]


def check_workspace(
    project_root: Path,
    workspace_root: Path,
    expected_build_script: str,
    expected_compile_commands: str,
    errors: list[str],
) -> None:
    vscode_root = workspace_root / ".vscode"
    tasks_path = vscode_root / "tasks.json"
    settings_path = vscode_root / "settings.json"
    cpp_properties_path = vscode_root / "c_cpp_properties.json"
    extensions_path = vscode_root / "extensions.json"

    for path in (tasks_path, settings_path, cpp_properties_path, extensions_path):
        if not path.is_file():
            errors.append(f"missing developer workspace metadata: {path.relative_to(project_root)}")

    task = build_task(load_json(tasks_path, errors), tasks_path.relative_to(project_root), errors)
    args = task.get("args") if task else None
    if not isinstance(args, list) or not args or args[-1] != expected_build_script:
        errors.append(
            f"{tasks_path.relative_to(project_root)} build task must invoke {expected_build_script}"
        )

    settings = load_json(settings_path, errors)
    if settings.get("C_Cpp.default.compileCommands") != expected_compile_commands:
        errors.append(
            f"{settings_path.relative_to(project_root)} must use compile commands {expected_compile_commands}"
        )

    cpp_properties = load_json(cpp_properties_path, errors)
    configurations = cpp_properties.get("configurations")
    if not isinstance(configurations, list) or not configurations:
        errors.append(f"{cpp_properties_path.relative_to(project_root)} must contain a C++ configuration")
    else:
        configuration = configurations[0]
        if configuration.get("compileCommands") != expected_compile_commands:
            errors.append(
                f"{cpp_properties_path.relative_to(project_root)} must use compile commands {expected_compile_commands}"
            )

    for path in (settings_path, cpp_properties_path):
        try:
            contents = path.read_text(encoding="utf-8")
        except OSError:
            continue
        if OLD_EGO_PATH in contents:
            errors.append(f"{path.relative_to(project_root)} still references {OLD_EGO_PATH}")
        if NEW_EGO_PATH not in contents:
            errors.append(f"{path.relative_to(project_root)} must reference {NEW_EGO_PATH}")


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--project-root", required=True, type=Path)
    args = parser.parse_args()
    project_root = args.project_root.resolve()
    ros_workspace = project_root / "future_aircraft_ws"
    errors: list[str] = []

    for path in (ros_workspace / ".catkin_workspace", ros_workspace / "src" / "CMakeLists.txt"):
        if not path.is_file():
            errors.append(f"missing Catkin workspace metadata: {path.relative_to(project_root)}")

    check_workspace(
        project_root,
        project_root,
        ROOT_BUILD_SCRIPT,
        ROOT_COMPILE_COMMANDS,
        errors,
    )
    check_workspace(
        project_root,
        ros_workspace,
        ROS_BUILD_SCRIPT,
        ROS_COMPILE_COMMANDS,
        errors,
    )

    if errors:
        for error in errors:
            print(f"[FAIL] {error}", file=sys.stderr)
        return 1
    print("[PASS] root and ROS workspace developer metadata are configured")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
