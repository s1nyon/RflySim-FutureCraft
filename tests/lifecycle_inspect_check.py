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

    # 6. Semantic port attribution: required MAVROS/roscore ports bound inside
    # WSL2 are reflected to Windows as an unidentifiable relay PID. When the
    # stack owns a LIVE component for that port's owner, the port must count as
    # owned (otherwise a READY stack can never pass pre-stop inspect).
    manifest6 = manifest_mod.new_manifest(stack_id="stack-20260808T120000Z-a1b2c3d4")
    ownership.register_process(
        manifest6, side="wsl", pid=500, pgid=500, role="wsl:mavros_uav1", name="roslaunch",
        command_line="roslaunch rflysim_mavros_px4.launch uav_namespace:=uav1",
        start_time_utc="2026-08-08T12:00:10Z", reason="t",
    )
    manifest6["required_ports"] = [
        {"port": 14600, "protocol": "udp", "owner": "uav1-mavros"},
        {"port": 11311, "protocol": "tcp", "owner": "ros_master"},
    ]
    mavros_proc = table_mod.ProcessInfo(
        pid=500, name="roslaunch", start_time_utc="2026-08-08T12:00:10Z",
        command_line="roslaunch rflysim_mavros_px4.launch uav_namespace:=uav1",
        parent_pid=1, pgid=500,
    )

    class RelayPortsProbe:
        def check(self, port, protocol):
            # Occupied by an unidentifiable Windows relay PID -> probe says unknown.
            return inspect.PortStatus(port, protocol, occupied=True, owned=False, detail="relay pid")

    report6 = inspect.inspect_stack(
        manifest6,
        win_table=table_mod.FakeProcessTable([]),
        wsl_table=table_mod.FakeProcessTable([mavros_proc]),
        ports_probe=RelayPortsProbe(),
        ros_probe=None,
    )
    owned_ports = {p.port: p for p in report6.ports if p.occupied}
    assert owned_ports[14600].owned is True, "14600 must be attributed to live stack MAVROS"
    assert owned_ports[11311].owned is False, "11311 without live roscore must stay unknown"
    assert report6.fail_closed is True, "11311 still unknown -> fail closed"

    # 7. WSL2 phantom relay: live stack PX4 instance reflects the required UDP
    # ports to Windows as an unidentifiable "px4" process; the port must be
    # attributed to the stack's alive px4 instance.
    manifest7 = manifest_mod.new_manifest(stack_id="stack-20260808T120000Z-a1b2c3d4")
    ownership.register_process(
        manifest7, side="wsl", pid=215, pgid=179, role="wsl:px4_uav1", name="px4",
        command_line="../bin/px4 -i 1 -d /mnt/d/PX4PSP/Firmware/build/px4_sitl_default/etc -s etc/init.d-posix/rcS",
        start_time_utc="2026-08-08T12:00:20Z", reason="t",
    )
    manifest7["required_ports"] = [{"port": 14600, "protocol": "udp", "owner": "uav1-mavros"}]
    px4_proc = table_mod.ProcessInfo(
        pid=215, name="px4", start_time_utc="2026-08-08T12:00:20Z",
        command_line="../bin/px4 -i 1 -d /mnt/d/PX4PSP/Firmware/build/px4_sitl_default/etc -s etc/init.d-posix/rcS",
        parent_pid=1, pgid=179,
    )
    report7 = inspect.inspect_stack(
        manifest7,
        win_table=table_mod.FakeProcessTable([]),
        wsl_table=table_mod.FakeProcessTable([px4_proc]),
        ports_probe=RelayPortsProbe(),
        ros_probe=None,
    )
    owned7 = {p.port: p for p in report7.ports if p.occupied}
    assert owned7[14600].owned is True, "14600 must be attributed to live stack PX4"
    assert report7.fail_closed is False

    # 8. Children of owned processes (e.g. mavros_node under owned roslaunch)
    # must not be classified unknown.
    manifest8 = manifest_mod.new_manifest(stack_id="stack-20260808T120000Z-a1b2c3d4")
    ownership.register_process(
        manifest8, side="wsl", pid=951, pgid=951, role="wsl:mavros_uav1", name="roslaunch",
        command_line="python3 /opt/ros/noetic/bin/roslaunch multi_uav_mission rflysim_mavros_px4.launch",
        start_time_utc="2026-08-08T12:00:30Z", reason="t",
    )
    roslaunch_proc = table_mod.ProcessInfo(
        pid=951, name="python3.10", start_time_utc="2026-08-08T12:00:30Z",
        command_line="/usr/bin/python3.10 /opt/ros/noetic/bin/roslaunch multi_uav_mission rflysim_mavros_px4.launch uav_namespace:=uav1",
        parent_pid=628, pgid=951,
    )
    mavros_node = table_mod.ProcessInfo(
        pid=1036, name="mavros_node", start_time_utc="2026-08-08T12:00:31Z",
        command_line="/opt/ros/noetic/lib/mavros/mavros_node __name:=mavros",
        parent_pid=951, pgid=1036,
    )
    report8 = inspect.inspect_stack(
        manifest8,
        win_table=table_mod.FakeProcessTable([]),
        wsl_table=table_mod.FakeProcessTable([roslaunch_proc, mavros_node]),
        ports_probe=CleanPortsProbe(),
        ros_probe=None,
    )
    assert report8.unknown_suspicious == [], "child of owned process must not be unknown"

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
