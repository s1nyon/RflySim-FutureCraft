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

    # 4. A foreign WSL process may reuse BOTH the recorded leader PID and its
    # numeric PGID.  The present leader identity mismatch takes precedence over
    # group membership: this is stale PID reuse, not an owned orphan.
    manifest4 = manifest_mod.new_manifest(stack_id="stack-20260808T120000Z-a1b2c3d4")
    ownership.register_process(
        manifest4, side="wsl", pid=737, pgid=737, role="wsl:sensor_bridge_uav2", name="python3",
        command_line="python3 /project/rflysim_sensor_bridge.py --copter-id 2",
        start_time_utc="2026-09-09T07:45:14Z", reason="created with setsid",
    )
    foreign_reused_leader = table_mod.ProcessInfo(
        pid=737, name="bash", start_time_utc="2026-09-10T02:12:18Z",
        command_line="/bin/bash --init-file /root/.vscode-server/shellIntegration-bash.sh",
        parent_pid=700, pgid=737,
    )
    reused_group_report = inspect.inspect_stack(
        manifest4,
        win_table=table_mod.FakeProcessTable([]),
        wsl_table=table_mod.FakeProcessTable([foreign_reused_leader]),
        ports_probe=CleanPortsProbe(),
        ros_probe=None,
    )
    assert len(reused_group_report.stale) == 1
    assert reused_group_report.stale[0].entry["pid"] == 737
    assert reused_group_report.orphans == [], "reused leader PID/PGID must not become owned_orphan"
    assert reused_group_report.fail_closed is True

    # 5. The same registered process may legitimately exec into its full
    # sensor-bridge argv.  Same PID/start-time plus a role-specific fragment is
    # still the owned leader, not stale reuse.
    transformed_bridge = table_mod.ProcessInfo(
        pid=737, name="python3", start_time_utc="2026-09-09T07:45:17Z",
        command_line="python3 /project/rflysim_sensor_bridge.py --copter-id 2 --sensor-mode lidar_only",
        parent_pid=700, pgid=737,
    )
    transformed_report = inspect.inspect_stack(
        manifest4,
        win_table=table_mod.FakeProcessTable([]),
        wsl_table=table_mod.FakeProcessTable([transformed_bridge]),
        ports_probe=CleanPortsProbe(),
        ros_probe=None,
    )
    assert transformed_report.stale == []
    assert transformed_report.orphans == []
    assert transformed_report.owned[0].status == "owned_and_alive"
    assert transformed_report.fail_closed is False

    # 6. owned orphan: leader exited but registered PGID still has processes.
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

    # 9. WSL exec-session relaxation must be a conjunction of role-specific
    #    argv fragments; a single generic string ("mavros", "--copter-id 1",
    #    "tail -f /dev/null") must never transfer ownership on its own.  Every
    #    case below reuses the recorded PID with a start time inside the five
    #    second tolerance, so only the argv evidence decides the classification.
    def wsl_session_case(role, recorded_cmd, live_cmd, *, pid=640,
                         granted="at_creation",
                         stack_id="stack-20260910T040000Z-abcd1234",
                         recorded_start="2026-09-10T04:00:00Z",
                         live_start="2026-09-10T04:00:03Z"):
        case_manifest = manifest_mod.new_manifest(stack_id=stack_id)
        extras = None
        if granted != "at_creation":
            extras = {
                "reason": "spawn attested",
                "ownership_parent_role": "wsl:px4_build_session",
                "stack_marker": {"name": "RFLY_STACK_ID", "value": stack_id},
                "ownership_evidence": {"marker_match": True},
            }
        ownership.register_process(
            case_manifest, side="wsl", pid=pid, pgid=pid, role=role, name="proc",
            command_line=recorded_cmd, start_time_utc=recorded_start, reason="t",
            ownership_extras=extras,
        )
        case_proc = table_mod.ProcessInfo(
            pid=pid, name="proc", start_time_utc=live_start,
            command_line=live_cmd, parent_pid=1, pgid=pid,
        )
        return case_manifest, case_proc

    def session_status(case_manifest, case_proc, marker_probe=None):
        report = inspect.inspect_stack(
            case_manifest,
            win_table=table_mod.FakeProcessTable([]),
            wsl_table=table_mod.FakeProcessTable([case_proc]),
            ports_probe=CleanPortsProbe(),
            ros_probe=None,
            session_marker_probe=marker_probe,
        )
        if report.stale:
            return "stale"
        if report.orphans:
            return "orphan"
        assert len(report.owned) == 1, report.owned
        return report.owned[0].status

    mavros_recorded = (
        "bash -lc source /opt/ros/noetic/setup.bash; roslaunch multi_uav_mission "
        "rflysim_mavros_px4.launch uav_namespace:=uav1 tgt_system:=1"
    )
    mavros_uav1_live = (
        "/usr/bin/python3 /opt/ros/noetic/bin/roslaunch multi_uav_mission "
        "rflysim_mavros_px4.launch uav_namespace:=uav1 "
        "fcu_url:=udp://:14601@127.0.0.1:14600 tgt_system:=1"
    )
    mavros_uav2_live = (
        "/usr/bin/python3 /opt/ros/noetic/bin/roslaunch multi_uav_mission "
        "rflysim_mavros_px4.launch uav_namespace:=uav2 "
        "fcu_url:=udp://:14611@127.0.0.1:14610 tgt_system:=2"
    )

    # 9a. The verified in-place exec transformation stays owned.
    assert session_status(*wsl_session_case("wsl:mavros_uav1", mavros_recorded, mavros_uav1_live)) \
        == "owned_and_alive"

    # 9b. UAV1 entry, UAV2 live argv (role swap) -> stale, never owned.
    assert session_status(*wsl_session_case("wsl:mavros_uav1", mavros_recorded, mavros_uav2_live)) \
        == "stale"

    # 9c. A foreign process inside the same window whose argv merely contains
    #     "mavros" must not inherit ownership.
    assert session_status(*wsl_session_case(
        "wsl:mavros_uav1", mavros_recorded,
        "/usr/bin/python3 /opt/ros/noetic/lib/mavros/mavros_node __name:=mavros",
    )) == "stale"

    # 9d. sensor bridge: the script name AND the copter id must both match.
    bridge_recorded = "python3 .../rflysim_sensor_bridge.py --copter-id 1 --sensor-mode lidar_only"
    bridge_live = (
        "python3 /project/future_aircraft_ws/src/multi_uav_mission/scripts/rflysim_sensor_bridge.py "
        "--config /project/config/rflysim_sensor_uav1.json --change-mode 1 --copter-id 1 "
        "--sensor-seq-id 0 --udp-port 9999 --sensor-mode lidar_only --keepalive"
    )
    assert session_status(*wsl_session_case("wsl:sensor_bridge_uav1", bridge_recorded, bridge_live)) \
        == "owned_and_alive"
    assert session_status(*wsl_session_case(
        "wsl:sensor_bridge_uav1", bridge_recorded,
        "python3 /tmp/unrelated_tool.py --copter-id 1 --watch",
    )) == "stale"
    assert session_status(*wsl_session_case(
        "wsl:sensor_bridge_uav1", bridge_recorded,
        bridge_live.replace("--copter-id 1", "--copter-id 2"),
    )) == "stale"

    # 9e. px4-mavlink: the MAVLink link instance must match.
    mavlink_recorded = (
        "/mnt/d/PX4PSP/Firmware/build/px4_sitl_default/bin/px4-mavlink "
        "--instance 1 start -u 14600 -o 14601 -r 4000000"
    )
    assert session_status(*wsl_session_case("wsl:px4_mavlink_uav1", mavlink_recorded, mavlink_recorded)) \
        == "owned_and_alive"
    assert session_status(*wsl_session_case(
        "wsl:px4_mavlink_uav1", mavlink_recorded,
        mavlink_recorded.replace("--instance 1", "--instance 2"),
    )) == "stale"

    # 9f. The exec exception is only valid for at_creation ownership; a
    #     spawn_attested entry never inherits it, even with a perfect argv.
    assert session_status(*wsl_session_case(
        "wsl:sensor_bridge_uav1", bridge_recorded, bridge_live, granted="spawn_attested",
    )) == "stale"

    # 9g. The five second window still applies to a matching argv.
    assert session_status(*wsl_session_case(
        "wsl:px4_mavlink_uav1", mavlink_recorded, mavlink_recorded,
        live_start="2026-09-10T04:01:00Z",
    )) == "stale"

    # 9h. The SITL wrapper session execs its last `bash -lic` command in place,
    # so its live argv is only the generic keepalive command.  Ownership then
    # rests on the launcher-inherited RFLY_STACK_ID marker, never on the argv.
    class SessionMarkerProbe:
        def __init__(self, verified):
            self.verified = bool(verified)
            self.calls = []

        def __call__(self, pid, stack_id):
            self.calls.append((int(pid), str(stack_id)))
            return self.verified

    build_recorded = "sitl_multiple_run_rfly.sh"
    build_keepalive = "tail -f /dev/null"
    marker_ok = SessionMarkerProbe(True)
    build_manifest, build_proc = wsl_session_case(
        "wsl:px4_build_session", build_recorded, build_keepalive,
        stack_id="stack-20260910T040000Z-abcd1234",
    )
    assert session_status(build_manifest, build_proc, marker_ok) == "owned_and_alive"
    assert marker_ok.calls == [(640, "stack-20260910T040000Z-abcd1234")], marker_ok.calls

    # 9i. Same keepalive argv, marker belongs to a different stack (or is
    #     otherwise unverifiable) -> stale, never owned.
    marker_denied = SessionMarkerProbe(False)
    assert session_status(build_manifest, build_proc, marker_denied) == "stale"

    # 9j. No marker probe at all -> fail closed, never owned.
    assert session_status(build_manifest, build_proc) == "stale"

    # 9k. A foreign process at the recorded PID whose argv has no keepalive
    #     command stays stale even when the marker probe would accept it.
    foreign_shell = "/bin/bash --init-file /root/.vscode-server/shellIntegration-bash.sh"
    assert session_status(*wsl_session_case(
        "wsl:px4_build_session", build_recorded, foreign_shell,
    ), SessionMarkerProbe(True)) == "stale"

    # 9l. The marker helper WSL path must resolve to the real frozen helper.
    helper_wsl = inspect.default_wsl_ops_helper_path()
    assert helper_wsl.startswith("/mnt/"), helper_wsl
    assert helper_wsl.endswith("/scripts/wsl/live_stack_wsl_ops.sh"), helper_wsl
    helper_parts = helper_wsl.split("/")
    helper_windows = Path(
        helper_parts[2].upper() + ":\\" + "\\".join(helper_parts[3:])
    )
    assert helper_windows.is_file(), helper_windows

    # 9m. Remaining launcher exec shapes, as produced by the frozen start
    #     chain, must stay owned (each requires two fragments).
    project_wsl = "/mnt/d/PX4PSP/RflySimAPIs/8.RflySimVision/3.CustExps/e13.RobotCom26Adv/future_aircraft_sim"
    assert session_status(*wsl_session_case(
        "wsl:stage2_launcher", "stage2_two_mavros.sh",
        f"bash {project_wsl}/scripts/wsl/stage2_two_mavros.sh",
    )) == "owned_and_alive"
    assert session_status(*wsl_session_case(
        "wsl:fastlio_session", "stage7_live_fastlio_dual.sh",
        f"bash {project_wsl}/scripts/wsl/stage7_live_fastlio_dual.sh",
    )) == "owned_and_alive"
    assert session_status(*wsl_session_case(
        "wsl:fastlio", "roslaunch multi_uav_mission rflysim_fastlio_dual.launch rviz:=false",
        "/usr/bin/python3 /opt/ros/noetic/bin/roslaunch multi_uav_mission "
        "rflysim_fastlio_dual.launch rviz:=false",
    )) == "owned_and_alive"
    assert session_status(*wsl_session_case(
        "wsl:ego_swarm_session",
        "stage7_live_ego_swarm_dual.sh -> roslaunch multi_uav_mission rflysim_ego_swarm_dual.launch",
        "/usr/bin/python3 /opt/ros/noetic/bin/roslaunch multi_uav_mission "
        "rflysim_ego_swarm_dual.launch",
    )) == "owned_and_alive"
    # A launcher session started from a copy outside scripts/wsl/ is not the
    # registered one and must stay stale.
    assert session_status(*wsl_session_case(
        "wsl:stage2_launcher", "stage2_two_mavros.sh",
        "/tmp/copy/stage2_two_mavros.sh",
    )) == "stale"

    # 6. JSON serializable.
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
