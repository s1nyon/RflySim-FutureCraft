#!/usr/bin/env python3
"""Stack manifest contract: schema, stack_id, fingerprint, PID-reuse protection, ownership records."""

from __future__ import annotations

import argparse
import importlib.util
import json
import re
import sys
import tempfile
from datetime import datetime, timezone
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
    parser.add_argument("--manifest-module", required=True, type=Path)
    parser.add_argument("--process-table-module", required=True, type=Path)
    parser.add_argument("--ownership-module", required=True, type=Path)
    args = parser.parse_args()

    manifest_mod = load_module("stack_manifest", args.manifest_module)
    table_mod = load_module("process_table", args.process_table_module)
    ownership = load_module("stack_ownership", args.ownership_module)

    # 1. stack_id: format and uniqueness
    ids = {manifest_mod.generate_stack_id() for _ in range(50)}
    assert len(ids) == 50, "stack_id must be unique"
    for sid in ids:
        assert re.fullmatch(r"stack-\d{8}T\d{6}Z-[0-9a-f]{8}", sid), f"bad stack_id: {sid}"

    # 2. manifest schema validation
    manifest = manifest_mod.new_manifest(
        stack_id="stack-20260808T120000Z-a1b2c3d4",
        git_commit="8c74d51c4b817bed7454d2504e9131cc3e5d65f4",
        launcher={
            "kind": "scheduled_task",
            "identity": "\\FutureAircraftSim_LiveStack_stack-20260808T120000Z-a1b2c3d4",
        },
        ros_master={"uri": "http://127.0.0.1:11311", "host": "127.0.0.1", "port": 11311},
    )
    manifest_mod.validate_manifest(manifest)
    assert manifest["schema_version"] == 1
    assert manifest["stack_id"] == "stack-20260808T120000Z-a1b2c3d4"
    assert manifest["git_commit"] == "8c74d51c4b817bed7454d2504e9131cc3e5d65f4"
    assert manifest["launcher"]["identity"].startswith("\\FutureAircraftSim_LiveStack_")
    assert manifest["ros_master"]["uri"] == "http://127.0.0.1:11311"

    broken = dict(manifest)
    del broken["stack_id"]
    try:
        manifest_mod.validate_manifest(broken)
        raise AssertionError("missing stack_id must be rejected")
    except ValueError:
        pass

    # 3. save/load roundtrip
    with tempfile.TemporaryDirectory() as tmp:
        path = Path(tmp) / "stack_manifest.json"
        manifest_mod.save_manifest(manifest, path)
        loaded = manifest_mod.load_manifest(path)
        assert loaded == manifest
        assert manifest_mod.manifest_dir(Path(tmp), manifest["stack_id"]) == Path(tmp) / "logs" / "live_stack" / manifest["stack_id"]
        assert manifest_mod.manifest_path(Path(tmp), manifest["stack_id"]).name == "stack_manifest.json"

    # 4. command-line fingerprint: normalization and discrimination
    fp_a = manifest_mod.command_line_fingerprint('  "C:\\Program Files\\App\\app.exe" --flag=1  ')
    fp_b = manifest_mod.command_line_fingerprint('"C:\\Program Files\\App\\app.exe" --flag=1')
    fp_c = manifest_mod.command_line_fingerprint('"C:\\Program Files\\App\\app.exe" --flag=2')
    assert fp_a == fp_b, "fingerprint must normalize whitespace/case"
    assert fp_a != fp_c, "fingerprint must differ when command line differs"
    assert re.fullmatch(r"[0-9a-f]{16}", fp_a)

    # 5. PID-reuse protection
    entry = {
        "pid": 100,
        "name": "app",
        "start_time_utc": "2026-08-08T12:00:00Z",
        "command_line": '"C:\\app.exe" --flag=1',
        "role": "test",
    }
    same_proc = table_mod.ProcessInfo(
        pid=100,
        name="app",
        start_time_utc="2026-08-08T12:00:00Z",
        command_line='"C:\\app.exe" --flag=1',
        parent_pid=1,
    )
    reused_proc = table_mod.ProcessInfo(
        pid=100,
        name="app",
        start_time_utc="2026-08-08T12:00:05Z",
        command_line='"C:\\app.exe" --flag=1',
        parent_pid=1,
    )
    different_cmd = table_mod.ProcessInfo(
        pid=100,
        name="app",
        start_time_utc="2026-08-08T12:00:00Z",
        command_line='"C:\\other.exe" --flag=9',
        parent_pid=1,
    )
    assert manifest_mod.entry_matches_process(entry, same_proc) is True
    assert manifest_mod.entry_matches_process(entry, reused_proc) is False, "PID reuse must not match"
    assert manifest_mod.entry_matches_process(entry, different_cmd) is False, "command-line mismatch must not match"

    # 6. ownership recording: windows descendants + wsl snapshot roles
    launcher = table_mod.ProcessInfo(pid=1000, name="cmd.exe", start_time_utc="2026-08-08T12:00:00Z",
                                     command_line='cmd /c call start_predicted_course_two_uav.bat', parent_pid=900)
    child = table_mod.ProcessInfo(pid=1001, name="RflySim3D", start_time_utc="2026-08-08T12:00:03Z",
                                  command_line='"D:\\PX4PSP\\RflySim3D\\RflySim3D.exe" --map SLAMScene', parent_pid=1000)
    grandchild = table_mod.ProcessInfo(pid=1002, name="CopterSim", start_time_utc="2026-08-08T12:00:05Z",
                                       command_line='"D:\\PX4PSP\\CopterSim\\CopterSim.exe"', parent_pid=1001)
    unrelated = table_mod.ProcessInfo(pid=2000, name="notepad.exe", start_time_utc="2026-08-08T12:00:00Z",
                                      command_line='notepad.exe', parent_pid=900)
    table = table_mod.FakeProcessTable([launcher, child, grandchild, unrelated])
    ownership.set_launcher(manifest, kind="scheduled_task",
                           identity="\\FutureAircraftSim_LiveStack_stack-20260808T120000Z-a1b2c3d4",
                           pid=1000, command_line=launcher.command_line)
    recorded = ownership.record_windows_processes(manifest, table, launcher_pid=1000)
    recorded_pids = {entry["pid"] for entry in recorded}
    assert recorded_pids == {1000, 1001, 1002}, f"must record launcher descendants only: {recorded_pids}"
    assert all(entry["start_time_utc"] for entry in recorded)
    assert all(entry["command_line"] for entry in recorded)
    assert manifest["launcher"]["pid"] == 1000

    wsl_lines = [
        "500 500 1 Sat Aug  8 12:00:10 2026 /opt/ros/noetic/bin/roscore",
        "510 500 1 Sat Aug  8 12:00:12 2026 /usr/bin/python3 .../rflysim_mavros_px4.launch uav_namespace:=uav1 fcu_url:=udp://:14601@127.0.0.1:14600",
        "511 500 1 Sat Aug  8 12:00:12 2026 /usr/bin/python3 .../rflysim_mavros_px4.launch uav_namespace:=uav2 fcu_url:=udp://:14611@127.0.0.1:14610",
        "520 500 1 Sat Aug  8 12:00:14 2026 /mnt/d/PX4PSP/Firmware/build/px4_sitl_default/bin/px4 -s etc/init.d/rcS",
    ]
    wsl_recorded = ownership.record_wsl_processes(manifest, wsl_lines)
    roles = {entry["pid"]: entry["role"] for entry in wsl_recorded}
    assert roles[500] == "wsl:roscore"
    assert roles[510] == "wsl:mavros_uav1"
    assert roles[511] == "wsl:mavros_uav2"
    assert roles[520] == "wsl:px4_sitl"

    ownership.set_simulation_instance_id(manifest, "px4-0123456789abcdef")
    assert manifest["simulation_instance_id"] == "px4-0123456789abcdef"
    ownership.set_ros_master(manifest, "http://127.0.0.1:11311")
    assert manifest["ros_master"]["port"] == 11311

    # 7. stop record
    ownership.record_stop(manifest, reason="user requested graceful stop", clean=True, force_reasons=[])
    assert manifest["stop"]["clean"] is True
    assert manifest["stop"]["last_stop_reason"] == "user requested graceful stop"

    manifest_mod.validate_manifest(manifest)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
