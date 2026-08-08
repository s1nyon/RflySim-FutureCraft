#!/usr/bin/env python3
"""Registration-at-creation ownership: no name/regex claiming may exist; only explicit registration grants ownership."""

from __future__ import annotations

import argparse
import importlib
import importlib.util
import sys
from pathlib import Path


def load_module(name: str, module_path: Path):
    module_path = Path(module_path).resolve()
    if module_path.parent.name == "lifecycle":
        sys.path.insert(0, str(module_path.parent.parent))
        importlib.import_module("lifecycle")
        return importlib.import_module(f"lifecycle.{name}")
    sys.path.insert(0, str(module_path.parent))
    spec = importlib.util.spec_from_file_location(name, str(module_path))
    if spec is None or spec.loader is None:
        raise RuntimeError(f"cannot load module: {module_path}")
    module = importlib.util.module_from_spec(spec)
    sys.modules[name] = module
    spec.loader.exec_module(module)
    return module


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--ownership-module", required=True, type=Path)
    parser.add_argument("--manifest-module", required=True, type=Path)
    args = parser.parse_args()

    ownership = load_module("stack_ownership", args.ownership_module)
    manifest_mod = load_module("stack_manifest", args.manifest_module)

    # The banned claiming helpers must be gone from the ownership module.
    source = Path(args.ownership_module).read_text(encoding="utf-8")
    for banned in ("record_windows_processes", "record_wsl_processes", "find_descendants"):
        assert banned not in source, f"scanning-based ownership helper must be removed: {banned}"

    manifest = manifest_mod.new_manifest(
        stack_id="stack-20260808T120000Z-a1b2c3d4",
        launcher={"kind": "batch", "identity": "test"},
    )

    # Only explicit registration grants ownership; unknown processes must never be auto-adopted.
    ownership.register_process(
        manifest, side="wsl", pid=500, pgid=500, role="wsl:roscore", name="roscore",
        command_line="/opt/ros/noetic/bin/roscore",
        start_time_utc="2026-08-08T12:00:10Z",
        reason="created by stage2_two_mavros.sh (setsid)",
    )
    assert len(manifest["wsl_processes"]) == 1
    assert manifest["wsl_processes"][0]["ownership"]["granted"] == "at_creation"

    spawn = ownership.register_process(
        manifest, side="wsl", pid=501, pgid=501, role="wsl:px4_uav1", name="px4",
        command_line="/mnt/d/PX4PSP/Firmware/build/px4_sitl_default/bin/px4 -i 1",
        start_time_utc="2026-08-08T12:00:16Z",
        reason="spawned by registered SITL session (marker-attested)",
        ownership_extras={
            "granted": "spawn_attested",
            "ownership_parent_role": "wsl:px4_build_session",
            "stack_marker": {"name": "RFLY_STACK_ID", "value": manifest["stack_id"]},
            "ownership_evidence": {"marker_match": True, "px4_instance_index": 1},
        },
    )
    assert spawn["ownership"]["granted"] == "spawn_attested"

    # Launcher / ROS master / sim-id metadata helpers.
    ownership.set_launcher(manifest, kind="scheduled_task", identity="\\Task", pid=1000, command_line="cmd /c call start.bat")
    assert manifest["launcher"]["pid"] == 1000
    ownership.set_ros_master(manifest, "http://127.0.0.1:11311")
    assert manifest["ros_master"]["port"] == 11311
    ownership.set_simulation_instance_id(manifest, "px4-0123456789abcdef")
    assert manifest["simulation_instance_id"] == "px4-0123456789abcdef"
    manifest_mod.validate_manifest(manifest)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
