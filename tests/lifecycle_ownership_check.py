#!/usr/bin/env python3
"""Ownership recording: Windows process-tree descendants and WSL snapshot role mapping."""

from __future__ import annotations

import argparse
import importlib.util
import sys
from pathlib import Path


def load_module(name: str, module_path: Path):
    module_path = Path(module_path).resolve()
    if module_path.parent.name == "lifecycle":
        sys.path.insert(0, str(module_path.parent.parent))
        import importlib

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
    parser.add_argument("--process-table-module", required=True, type=Path)
    parser.add_argument("--manifest-module", required=True, type=Path)
    args = parser.parse_args()

    ownership = load_module("stack_ownership", args.ownership_module)
    table_mod = load_module("process_table", args.process_table_module)
    manifest_mod = load_module("stack_manifest", args.manifest_module)

    manifest = manifest_mod.new_manifest(
        stack_id="stack-20260808T120000Z-a1b2c3d4",
        launcher={"kind": "batch", "identity": "scripts/start_predicted_course_two_uav.bat"},
    )

    # Windows: only descendants of the launcher may be recorded; siblings stay out.
    launcher = table_mod.ProcessInfo(pid=1000, name="cmd.exe", start_time_utc="2026-08-08T12:00:00Z",
                                     command_line='cmd /c call "D:\\p\\start.bat"', parent_pid=900)
    a = table_mod.ProcessInfo(pid=1001, name="RflySim3D", start_time_utc="2026-08-08T12:00:03Z",
                              command_line='"D:\\p\\RflySim3D.exe" --map SLAMScene', parent_pid=1000)
    b = table_mod.ProcessInfo(pid=1002, name="CopterSim", start_time_utc="2026-08-08T12:00:05Z",
                              command_line='"D:\\p\\CopterSim.exe"', parent_pid=1001)
    sibling = table_mod.ProcessInfo(pid=2000, name="RflySim3D", start_time_utc="2026-08-08T12:30:00Z",
                                    command_line='"D:\\other\\RflySim3D.exe"', parent_pid=900)
    ownership.set_launcher(manifest, kind="scheduled_task", identity="\\FutureAircraftSim_LiveStack_xyz",
                           pid=1000, command_line=launcher.command_line)
    recorded = ownership.record_windows_processes(
        manifest, table_mod.FakeProcessTable([launcher, a, b, sibling]), launcher_pid=1000
    )
    assert {e["pid"] for e in recorded} == {1000, 1001, 1002}
    assert sibling.pid not in {e["pid"] for e in recorded}, "sibling process must not be owned"

    # WSL snapshot role mapping across all known roles
    wsl_lines = [
        "500 500 1 Sat Aug  8 12:00:10 2026 /opt/ros/noetic/bin/roscore",
        "501 500 1 Sat Aug  8 12:00:11 2026 /mnt/d/PX4PSP/Firmware/build/px4_sitl_default/bin/px4-mavlink --instance 1 start -u 14600 -o 14601 -r 4000000",
        "510 500 1 Sat Aug  8 12:00:12 2026 /usr/bin/python3 /opt/ros/noetic/lib/mavros/mavros_node ... rflysim_mavros_px4.launch uav_namespace:=uav1",
        "511 500 1 Sat Aug  8 12:00:12 2026 /usr/bin/python3 /opt/ros/noetic/lib/mavros/mavros_node ... rflysim_mavros_px4.launch uav_namespace:=uav2",
        "520 500 1 Sat Aug  8 12:00:14 2026 /mnt/d/PX4PSP/Firmware/build/px4_sitl_default/bin/px4 -s etc/init.d/rcS",
        "530 500 1 Sat Aug  8 12:00:15 2026 /usr/bin/python3 .../rflysim_sensor_bridge.py --copter-id 1",
        "540 500 1 Sat Aug  8 12:00:16 2026 /usr/bin/python3 .../rflysim_fastlio_dual.launch",
        "550 500 1 Sat Aug  8 12:00:17 2026 /usr/bin/python3 .../rflysim_ego_swarm_dual.launch",
        "560 500 1 Sat Aug  8 12:00:18 2026 /usr/bin/python3 .../mission_executor.py --backend ros",
        "570 500 1 Sat Aug  8 12:00:19 2026 /usr/bin/python3 .../narrow_course_cloud_server.py",
        "580 500 1 Sat Aug  8 12:00:20 2026 /bin/bash .../stage2_two_mavros.sh",
        "590 500 1 Sat Aug  8 12:00:21 2026 /usr/bin/python3 .../other_node.py",
    ]
    recorded_wsl = ownership.record_wsl_processes(manifest, wsl_lines)
    roles = {e["pid"]: e["role"] for e in recorded_wsl}
    assert roles[500] == "wsl:roscore"
    assert roles[501] == "wsl:px4_mavlink"
    assert roles[510] == "wsl:mavros_uav1"
    assert roles[511] == "wsl:mavros_uav2"
    assert roles[520] == "wsl:px4_sitl"
    assert roles[530] == "wsl:sensor_bridge"
    assert roles[540] == "wsl:fastlio"
    assert roles[550] == "wsl:ego_swarm"
    assert roles[560] == "wsl:mission_executor"
    assert roles[570] == "wsl:course_cloud"
    assert roles[580] == "wsl:stage2_script"
    assert 590 not in roles, "unrecognized process must not be recorded as owned"

    assert manifest["wsl_processes"]
    manifest_mod.validate_manifest(manifest)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
