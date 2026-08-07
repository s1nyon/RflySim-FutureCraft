#!/usr/bin/env python3
"""Read-only inspect contract: owned states, unknown fail-closed, stale PID reuse, ports, ROS."""

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
    parser.add_argument("--inspect-module", required=True, type=Path)
    parser.add_argument("--process-table-module", required=True, type=Path)
    parser.add_argument("--manifest-module", required=True, type=Path)
    args = parser.parse_args()

    inspect = load_module("stack_inspect", args.inspect_module)
    table_mod = load_module("process_table", args.process_table_module)
    manifest_mod = load_module("stack_manifest", args.manifest_module)

    win_alive = table_mod.ProcessInfo(pid=111, name="RflySim3D", start_time_utc="2026-08-08T12:00:03Z",
                                      command_line='"D:\\PX4PSP\\RflySim3D\\RflySim3D.exe"', parent_pid=1000)
    win_exited = table_mod.ProcessInfo(pid=112, name="CopterSim", start_time_utc="2026-08-08T12:00:05Z",
                                       command_line='"D:\\PX4PSP\\CopterSim\\CopterSim.exe"', parent_pid=1000)
    unknown_gui = table_mod.ProcessInfo(pid=999, name="QGroundControl", start_time_utc="2026-08-08T12:10:00Z",
                                        command_line='"D:\\PX4PSP\\QGroundControl\\QGroundControl.exe"', parent_pid=1)
    wsl_px4 = table_mod.ProcessInfo(pid=520, name="px4", start_time_utc="2026-08-08T12:00:14Z",
                                    command_line="/mnt/d/PX4PSP/Firmware/build/px4_sitl_default/bin/px4 -s etc/init.d/rcS",
                                    parent_pid=500, pgid=500)

    manifest = manifest_mod.new_manifest(
        stack_id="stack-20260808T120000Z-a1b2c3d4",
        launcher={"kind": "batch", "identity": "scripts/start_predicted_course_two_uav.bat"},
    )
    manifest["windows_processes"] = [
        {
            "pid": 111,
            "name": "RflySim3D",
            "start_time_utc": "2026-08-08T12:00:03Z",
            "command_line": '"D:\\PX4PSP\\RflySim3D\\RflySim3D.exe"',
            "role": "gui:RflySim3D",
        },
        {
            "pid": 112,
            "name": "CopterSim",
            "start_time_utc": "2026-08-08T12:00:05Z",
            "command_line": '"D:\\PX4PSP\\CopterSim\\CopterSim.exe"',
            "role": "gui:CopterSim",
        },
    ]
    manifest["wsl_processes"] = [
        {
            "pid": 520,
            "pgid": 500,
            "name": "px4",
            "start_time_utc": "2026-08-08T12:00:14Z",
            "command_line": "/mnt/d/PX4PSP/Firmware/build/px4_sitl_default/bin/px4 -s etc/init.d/rcS",
            "role": "wsl:px4_sitl",
        }
    ]
    manifest["required_ports"] = [{"port": 14600, "protocol": "udp", "owner": "uav1-mavros"}]

    class FakePortsProbe:
        def check(self, port, protocol):
            return inspect.PortStatus(
                port=port, protocol=protocol, occupied=True, owned=False,
                detail="owned-by-unknown",
            )

    class CleanPortsProbe:
        def check(self, port, protocol):
            return inspect.PortStatus(
                port=port, protocol=protocol, occupied=False, owned=None, detail="free"
            )

    class FakeRosProbe:
        def roscore_alive(self):
            return True

        def mavros_connected(self, ns):
            return {"uav1": True, "uav2": False}[ns]

        def course_ready(self):
            return True

    # 1. owned alive + owned but exited + ROS statuses + port occupied by non-owned
    report = inspect.inspect_stack(
        manifest,
        win_table=table_mod.FakeProcessTable([win_alive, unknown_gui]),
        wsl_table=table_mod.FakeProcessTable([wsl_px4]),
        ports_probe=FakePortsProbe(),
        ros_probe=FakeRosProbe(),
    )
    by_pid = {item.entry["pid"]: item.status for item in report.owned}
    assert by_pid[111] == "owned_and_alive"
    assert by_pid[112] == "owned_but_exited"
    assert by_pid[520] == "owned_and_alive"
    assert report.ros.roscore_alive is True
    assert report.ros.mavros_uav1_connected is True
    assert report.ros.mavros_uav2_connected is False
    assert report.ros.course_ready is True
    assert any(p.port == 14600 and p.occupied and not p.owned for p in report.ports)

    # 2. unknown suspicious process -> fail closed
    unknown_pids = {p.pid for p in report.unknown_suspicious}
    assert 999 in unknown_pids, "QGroundControl not in manifest must be reported as unknown"
    assert report.fail_closed is True

    # 3. clean stack: no unknown, no stale -> not fail closed
    clean = inspect.inspect_stack(
        manifest,
        win_table=table_mod.FakeProcessTable([win_alive]),
        wsl_table=table_mod.FakeProcessTable([wsl_px4]),
        ports_probe=CleanPortsProbe(),
        ros_probe=FakeRosProbe(),
    )
    assert clean.unknown_suspicious == []
    assert clean.fail_closed is False

    # 4. stale PID reuse -> fail closed and classified, never matched as owned_and_alive
    reused = table_mod.ProcessInfo(pid=111, name="RflySim3D", start_time_utc="2026-08-08T14:00:00Z",
                                   command_line='"D:\\PX4PSP\\RflySim3D\\RflySim3D.exe"', parent_pid=1)
    stale_report = inspect.inspect_stack(
        manifest,
        win_table=table_mod.FakeProcessTable([reused]),
        wsl_table=table_mod.FakeProcessTable([wsl_px4]),
        ports_probe=CleanPortsProbe(),
        ros_probe=FakeRosProbe(),
    )
    stale_pids = {item.entry["pid"] for item in stale_report.stale}
    assert 111 in stale_pids
    assert stale_report.fail_closed is True
    assert all(item.status != "owned_and_alive" for item in stale_report.owned if item.entry["pid"] == 111)

    # 5. JSON-serializable report
    import json
    json.dumps(inspect.report_to_dict(stale_report))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
