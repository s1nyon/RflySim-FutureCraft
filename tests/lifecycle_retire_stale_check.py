#!/usr/bin/env python3
"""Contract for explicit metadata-only retirement of a proven-dead stack."""

from __future__ import annotations

import argparse
import copy
import importlib
import sys
from pathlib import Path


def load_lifecycle(module_path: Path):
    lifecycle_dir = module_path.resolve().parent
    sys.path.insert(0, str(lifecycle_dir.parent))
    importlib.import_module("lifecycle")
    return importlib.import_module(f"lifecycle.{module_path.stem}")


class MutableTable:
    def __init__(self, processes):
        self.processes = list(processes)

    def snapshot(self):
        return list(self.processes)


class PortsProbe:
    def __init__(self, inspect, occupied=False, detail=None):
        self.inspect = inspect
        self.occupied = occupied
        self.detail = detail or ("unknown owner" if occupied else "free")

    def check(self, port, protocol):
        return self.inspect.PortStatus(
            port=int(port), protocol=str(protocol), occupied=self.occupied,
            owned=False if self.occupied else None, detail=self.detail,
        )


class InactiveRos:
    def roscore_alive(self):
        return False

    def mavros_connected(self, _ns):
        return False

    def course_ready(self):
        return False


def proc(process_table, pid, name, start, command, *, pgid=None, parent=1):
    return process_table.ProcessInfo(
        pid=pid, name=name, start_time_utc=start, command_line=command,
        parent_pid=parent, pgid=pgid,
    )


def base_manifest(manifest_mod, ownership):
    value = manifest_mod.new_manifest("stack-20260831T173615Z-6d6e09b6")
    value["required_ports"] = [
        {"port": 14600, "protocol": "udp", "owner": "uav1-mavros"},
        {"port": 11311, "protocol": "tcp", "owner": "ros_master"},
    ]
    ownership.register_process(
        value, side="windows", pid=20072, role="gui:RflySim3D", name="RflySim3D",
        start_time_utc="2026-08-31T17:36:17Z",
        command_line="D:\\PX4PSP\\RflySim3D\\RflySim3D.exe -cmd=RflyChangeMapbyName-SLAMScene",
        reason="created at launch",
    )
    return value


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--retire-module", required=True, type=Path)
    parser.add_argument("--inspect-module", required=True, type=Path)
    parser.add_argument("--process-table-module", required=True, type=Path)
    parser.add_argument("--manifest-module", required=True, type=Path)
    parser.add_argument("--ownership-module", required=True, type=Path)
    args = parser.parse_args()

    retire = load_lifecycle(args.retire_module)
    inspect = load_lifecycle(args.inspect_module)
    process_table = load_lifecycle(args.process_table_module)
    manifest_mod = load_lifecycle(args.manifest_module)
    ownership = load_lifecycle(args.ownership_module)
    free_ports = PortsProbe(inspect)
    inactive_ros = InactiveRos()
    recorded_cmd = "D:\\PX4PSP\\RflySim3D\\RflySim3D.exe -cmd=RflyChangeMapbyName-SLAMScene"
    foreign_cmd = "C:\\Windows\\System32\\svchost.exe -k GraphicsPerfSvcGroup -s GraphicsPerfSvc"
    original = proc(process_table, 20072, "RflySim3D", "2026-08-31T17:36:17Z", recorded_cmd)
    foreign = proc(process_table, 20072, "svchost.exe", "2026-09-01T08:20:33Z", foreign_cmd)

    # A: an exact owned process still alive is never eligible.
    manifest_a = base_manifest(manifest_mod, ownership)
    plan_a = retire.build_retirement_plan(
        manifest_a, MutableTable([original]), MutableTable([]), free_ports, inactive_ros,
    )
    assert plan_a.eligible is False
    assert "owned_and_alive=1" in plan_a.denial_reasons

    # B: pre-existing Windows PID reuse is metadata-only; the foreign occupant survives.
    manifest_b = base_manifest(manifest_mod, ownership)
    win_b = MutableTable([foreign])
    plan_b = retire.build_retirement_plan(
        manifest_b, win_b, MutableTable([]), free_ports, inactive_ros,
    )
    assert plan_b.eligible is True, plan_b.denial_reasons
    assert plan_b.planned_process_signals == []
    assert plan_b.entries[0]["role"] == "gui:RflySim3D"
    assert plan_b.entries[0]["recorded_pid"] == 20072
    assert plan_b.entries[0]["recorded_identity"]["name"] == "RflySim3D"
    assert plan_b.entries[0]["observed_identity"]["name"] == "svchost.exe"
    assert plan_b.entries[0]["signal_sent"] is False
    executed_b = retire.execute_retirement(
        manifest_b, win_b, MutableTable([]), free_ports, inactive_ros,
        expected_plan_token=plan_b.plan_token,
    )
    assert executed_b.eligible is True
    assert win_b.snapshot() == [foreign], "foreign recycled PID must survive unchanged"
    assert manifest_b["windows_processes"] == []
    audit_b = manifest_b["stop"]["retired_stale_ownership"][-1]
    assert audit_b["observed_identity"]["name"] == "svchost.exe"
    assert audit_b["retirement_reason"] == "pid_identity_mismatch"
    assert audit_b["signal_sent"] is False

    # C: an already absent recorded PID can be retired normally.
    manifest_c = base_manifest(manifest_mod, ownership)
    plan_c = retire.build_retirement_plan(
        manifest_c, MutableTable([]), MutableTable([]), free_ports, inactive_ros,
    )
    assert plan_c.eligible is True
    assert plan_c.entries[0]["observed_identity"] is None
    assert plan_c.entries[0]["retirement_reason"] == "recorded_pid_absent"

    # D: stale plus another exact owned process alive is fail-closed.
    manifest_d = base_manifest(manifest_mod, ownership)
    ownership.register_process(
        manifest_d, side="windows", pid=222, role="gui:CopterSim", name="CopterSim",
        start_time_utc="2026-09-01T08:00:00Z", command_line="CopterSim.exe 1", reason="created",
    )
    copter = proc(process_table, 222, "CopterSim", "2026-09-01T08:00:00Z", "CopterSim.exe 1")
    plan_d = retire.build_retirement_plan(
        manifest_d, MutableTable([foreign, copter]), MutableTable([]), free_ports, inactive_ros,
    )
    assert plan_d.eligible is False and "owned_and_alive=1" in plan_d.denial_reasons

    # E: stale plus an owned WSL PGID/orphan is fail-closed.
    manifest_e = base_manifest(manifest_mod, ownership)
    ownership.register_process(
        manifest_e, side="wsl", pid=500, pgid=500, role="wsl:roscore", name="roscore",
        start_time_utc="2026-09-01T08:00:00Z", command_line="/opt/ros/noetic/bin/roscore", reason="setsid",
    )
    orphan = proc(
        process_table, 501, "rosmaster", "2026-09-01T08:00:01Z",
        "/opt/ros/noetic/bin/rosmaster", pgid=500, parent=1,
    )
    plan_e = retire.build_retirement_plan(
        manifest_e, MutableTable([foreign]), MutableTable([orphan]), free_ports, inactive_ros,
    )
    assert plan_e.eligible is False and "owned_orphan=1" in plan_e.denial_reasons

    # F: any unknown suspicious process is fail-closed.
    manifest_f = base_manifest(manifest_mod, ownership)
    unknown = proc(process_table, 999, "QGroundControl", "2026-09-01T08:00:00Z", "QGroundControl.exe")
    plan_f = retire.build_retirement_plan(
        manifest_f, MutableTable([foreign, unknown]), MutableTable([]), free_ports, inactive_ros,
    )
    assert plan_f.eligible is False and "unknown_suspicious=1" in plan_f.denial_reasons

    # F2: a suspicious stack process occupying the recorded recycled PID is
    # still activity, even though ordinary inspect classifies it only as stale.
    suspicious_reuse = proc(
        process_table, 20072, "QGroundControl", "2026-09-01T08:00:00Z", "QGroundControl.exe",
    )
    plan_f2 = retire.build_retirement_plan(
        manifest_f, MutableTable([suspicious_reuse]), MutableTable([]), free_ports, inactive_ros,
    )
    assert plan_f2.eligible is False
    assert "stale_pid_occupied_by_suspicious_process=1" in plan_f2.denial_reasons

    # G: any occupied required port is fail-closed, even if attribution is ambiguous.
    manifest_g = base_manifest(manifest_mod, ownership)
    plan_g = retire.build_retirement_plan(
        manifest_g, MutableTable([foreign]), MutableTable([]), PortsProbe(inspect, occupied=True), inactive_ros,
    )
    assert plan_g.eligible is False and "required_ports_not_clean=2" in plan_g.denial_reasons

    class AmbiguousTable(MutableTable):
        last_error = "snapshot failed"

    ambiguous = retire.build_retirement_plan(
        manifest_g, AmbiguousTable([]), MutableTable([]), free_ports, inactive_ros,
    )
    assert ambiguous.eligible is False
    assert any(reason.startswith("windows_process_probe_ambiguous=") for reason in ambiguous.denial_reasons)

    # H: Execute recaptures immediately before mutation; a changed process state aborts atomically.
    manifest_h = base_manifest(manifest_mod, ownership)
    before_h = copy.deepcopy(manifest_h)
    win_h = MutableTable([foreign])
    plan_h = retire.build_retirement_plan(
        manifest_h, win_h, MutableTable([]), free_ports, inactive_ros,
    )

    def introduce_unknown():
        win_h.processes.append(unknown)

    try:
        retire.execute_retirement(
            manifest_h, win_h, MutableTable([]), free_ports, inactive_ros,
            expected_plan_token=plan_h.plan_token, before_commit=introduce_unknown,
        )
    except retire.RetirementError as exc:
        assert "state changed" in str(exc).lower()
    else:
        raise AssertionError("TOCTOU state change must abort")
    assert manifest_h == before_h, "TOCTOU abort must leave manifest byte-equivalent in memory"

    # I: after success, ordinary inspect is clean and the foreign PID still exists.
    post_b = inspect.inspect_stack(
        manifest_b, win_table=win_b, wsl_table=MutableTable([]),
        ports_probe=free_ports, ros_probe=inactive_ros,
    )
    summary_b = inspect.summarize(post_b)
    assert summary_b["owned_and_alive"] == 0
    assert summary_b["stale_pid_reuse"] == 0
    assert summary_b["unknown_suspicious"] == 0
    assert summary_b["ports_occupied_by_unknown"] == 0
    assert post_b.fail_closed is False
    assert win_b.snapshot()[0].name == "svchost.exe"

    print("lifecycle_retire_stale_check: PASS")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
