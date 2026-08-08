#!/usr/bin/env python3
"""Read-only inspect: owned states, orphans, unknown fail-closed, stale PID reuse, ports, ROS."""

from __future__ import annotations

import argparse
import importlib
import importlib.util
import json
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
    parser.add_argument("--inspect-module", required=True, type=Path)
    parser.add_argument("--process-table-module", required=True, type=Path)
    parser.add_argument("--manifest-module", required=True, type=Path)
    parser.add_argument("--ownership-module", required=True, type=Path)
    args = parser.parse_args()

    inspect = load_module("stack_inspect", args.inspect_module)
    table_mod = load_module("process_table", args.process_table_module)
    manifest_mod = load_module("stack_manifest", args.manifest_module)
    ownership = load_module("stack_ownership", args.ownership_module)

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
        launcher={"kind": "batch", "identity": "test"},
    )
    ownership.register_process(
        manifest, side="windows", pid=111, role="gui:RflySim3D", name="RflySim3D",
        command_line='"D:\\PX4PSP\\RflySim3D\\RflySim3D.exe"', start_time_utc="2026-08-08T12:00:03Z", reason="t",
    )
    ownership.register_process(
        manifest, side="windows", pid=112, role="gui:CopterSim", name="CopterSim",
        command_line='"D:\\PX4PSP\\CopterSim\\CopterSim.exe"', start_time_utc="2026-08-08T12:00:05Z", reason="t",
    )
    ownership.register_process(
        manifest, side="wsl", pid=520, pgid=500, role="wsl:px4_sitl", name="px4",
        command_line="/mnt/d/PX4PSP/Firmware/build/px4_sitl_default/bin/px4 -s etc/init.d/rcS",
        start_time_utc="2026-08-08T12:00:14Z", reason="t",
    )
    manifest["required_ports"] = [{"port": 14600, "protocol": "udp", "owner": "uav1-mavros"}]

    class FakePortsProbe:
        def check(self, port, protocol):
            return inspect.PortStatus(port=port, protocol=protocol, occupied=True, owned=False, detail="unknown")

    class CleanPortsProbe:
        def check(self, port, protocol):
            return inspect.PortStatus(port=port, protocol=protocol, occupied=False, owned=None, detail="free")

    class FakeRosProbe:
        def roscore_alive(self):
            return True

        def mavros_connected(self, ns):
            return {"uav1": True, "uav2": False}[ns]

        def course_ready(self):
            return True

    # 1. owned alive/exited + unknown fail-closed + ports + ROS.
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
    assert report.ros.mavros_uav2_connected is False
    assert {p.pid for p in report.unknown_suspicious} == {999}
    assert report.fail_closed is True

    # 2. clean stack without unknown/stale.
    clean = inspect.inspect_stack(
        manifest,
        win_table=table_mod.FakeProcessTable([win_alive]),
        wsl_table=table_mod.FakeProcessTable([wsl_px4]),
        ports_probe=CleanPortsProbe(),
        ros_probe=FakeRosProbe(),
    )
    assert clean.unknown_suspicious == [] and clean.stale == [] and clean.orphans == []
    assert clean.fail_closed is False

    # 3. stale PID reuse -> fail closed.
    reused = table_mod.ProcessInfo(pid=111, name="RflySim3D", start_time_utc="2026-08-08T14:00:00Z",
                                   command_line='"D:\\PX4PSP\\RflySim3D\\RflySim3D.exe"', parent_pid=1)
    stale_report = inspect.inspect_stack(
        manifest,
        win_table=table_mod.FakeProcessTable([reused]),
        wsl_table=table_mod.FakeProcessTable([wsl_px4]),
        ports_probe=CleanPortsProbe(),
        ros_probe=None,
    )
    assert {item.entry["pid"] for item in stale_report.stale} == {111}
    assert stale_report.fail_closed is True

    # 4. owned orphan: leader exited but registered PGID still has processes.
    orphan = table_mod.ProcessInfo(pid=777, name="px4", start_time_utc="2026-08-08T12:00:15Z",
                                   command_line="/mnt/d/PX4PSP/Firmware/build/px4_sitl_default/bin/px4 -s etc/init.d/rcS",
                                   parent_pid=1, pgid=500)
    orphan_report = inspect.inspect_stack(
        manifest,
        win_table=table_mod.FakeProcessTable([win_alive]),
        wsl_table=table_mod.FakeProcessTable([orphan]),
        ports_probe=CleanPortsProbe(),
        ros_probe=None,
    )
    orphan_statuses = [item for item in orphan_report.owned if item.entry["pid"] == 520]
    assert any(item.status == "owned_orphan" for item in orphan_statuses), "orphan must be classified owned_orphan"
    assert len(orphan_report.orphans) == 1
    assert orphan_report.fail_closed is False, "owned orphans must not block stop (they are owned)"

    # 5. JSON serializable.
    json.dumps(inspect.report_to_dict(orphan_report))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
