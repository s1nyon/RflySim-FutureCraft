#!/usr/bin/env python3
"""Manifest v2 + registration-at-creation contract: schema, fingerprint, PID-reuse, ownership grant."""

from __future__ import annotations

import argparse
import importlib
import importlib.util
import re
import sys
import tempfile
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
    parser.add_argument("--manifest-module", required=True, type=Path)
    parser.add_argument("--process-table-module", required=True, type=Path)
    parser.add_argument("--ownership-module", required=True, type=Path)
    args = parser.parse_args()

    manifest_mod = load_module("stack_manifest", args.manifest_module)
    table_mod = load_module("process_table", args.process_table_module)
    ownership = load_module("stack_ownership", args.ownership_module)

    assert manifest_mod.SCHEMA_VERSION == 2

    # stack_id format/uniqueness
    ids = {manifest_mod.generate_stack_id() for _ in range(50)}
    assert len(ids) == 50
    for sid in ids:
        assert re.fullmatch(r"stack-\d{8}T\d{6}Z-[0-9a-f]{8}", sid)

    manifest = manifest_mod.new_manifest(
        stack_id="stack-20260808T120000Z-a1b2c3d4",
        git_commit="8c74d51c4b817bed7454d2504e9131cc3e5d65f4",
        launcher={"kind": "scheduled_task", "identity": "\\FutureAircraftSim_LiveStack_xyz"},
        ros_master={"uri": "http://127.0.0.1:11311", "host": "127.0.0.1", "port": 11311},
    )
    manifest_mod.validate_manifest(manifest)

    # Registration at creation: every entry must carry an explicit ownership grant.
    entry = ownership.register_process(
        manifest,
        side="windows",
        pid=111,
        role="gui:RflySim3D",
        name="RflySim3D",
        command_line='"D:\\PX4PSP\\RflySim3D\\RflySim3D.exe" -cmd=RflyChangeMapbyName-SLAMScene',
        start_time_utc="2026-08-08T12:00:03Z",
        reason="launcher captured PID via Start-Process -PassThru at creation",
    )
    assert entry["ownership"]["granted"] == "at_creation"
    assert entry["ownership"]["reason"].startswith("launcher captured PID")
    assert entry["ownership"]["granted_at_utc"]
    assert entry["pid"] == 111 and entry["role"] == "gui:RflySim3D"
    manifest_mod.validate_manifest(manifest)

    # Duplicate registration of the same pid+side must fail loudly (launcher bug).
    try:
        ownership.register_process(
            manifest, side="windows", pid=111, role="gui:CopterSim",
            name="CopterSim", command_line="x", reason="dup",
        )
        raise AssertionError("duplicate pid+side registration must raise")
    except ValueError:
        pass

    # WSL registration with PGID.
    wsl_entry = ownership.register_process(
        manifest,
        side="wsl",
        pid=520,
        pgid=520,
        role="wsl:px4_sitl",
        name="px4",
        command_line="/mnt/d/PX4PSP/Firmware/build/px4_sitl_default/bin/px4 -s etc/init.d/rcS",
        start_time_utc="2026-08-08T12:00:14Z",
        reason="created by stack SITL wrapper (setsid)",
    )
    assert wsl_entry["pgid"] == 520

    # Schema validation: entry without ownership must be rejected.
    broken = dict(manifest)
    broken["windows_processes"] = [dict(manifest["windows_processes"][0])]
    del broken["windows_processes"][0]["ownership"]
    try:
        manifest_mod.validate_manifest(broken)
        raise AssertionError("entry without ownership grant must be rejected")
    except ValueError:
        pass

    # Atomic save/load roundtrip.
    with tempfile.TemporaryDirectory() as tmp:
        path = Path(tmp) / "stack_manifest.json"
        manifest_mod.save_manifest(manifest, path)
        assert manifest_mod.load_manifest(path) == manifest
        assert manifest_mod.manifest_dir(Path(tmp), manifest["stack_id"]) == Path(tmp) / "logs" / "live_stack" / manifest["stack_id"]

    # Command-line fingerprint + PID-reuse protection.
    fp_a = manifest_mod.command_line_fingerprint('  "C:\\app.exe" --flag=1  ')
    fp_b = manifest_mod.command_line_fingerprint('"C:\\app.exe" --flag=1')
    fp_c = manifest_mod.command_line_fingerprint('"C:\\app.exe" --flag=2')
    assert fp_a == fp_b and fp_a != fp_c
    assert re.fullmatch(r"[0-9a-f]{16}", fp_a)

    same_proc = table_mod.ProcessInfo(
        pid=111, name="RflySim3D", start_time_utc="2026-08-08T12:00:03Z",
        command_line='"D:\\PX4PSP\\RflySim3D\\RflySim3D.exe" -cmd=RflyChangeMapbyName-SLAMScene', parent_pid=1,
    )
    reused_proc = table_mod.ProcessInfo(
        pid=111, name="RflySim3D", start_time_utc="2026-08-08T14:00:00Z",
        command_line='"D:\\PX4PSP\\RflySim3D\\RflySim3D.exe" -cmd=RflyChangeMapbyName-SLAMScene', parent_pid=1,
    )
    other_cmd = table_mod.ProcessInfo(
        pid=111, name="RflySim3D", start_time_utc="2026-08-08T12:00:03Z",
        command_line='"D:\\other\\RflySim3D.exe"', parent_pid=1,
    )
    assert manifest_mod.entry_matches_process(entry, same_proc) is True
    assert manifest_mod.entry_matches_process(entry, reused_proc) is False
    assert manifest_mod.entry_matches_process(entry, other_cmd) is False

    # Stop record carries failure reasons.
    ownership.record_stop(manifest, reason="test", clean=False, failure_reasons=["still alive"])
    assert manifest["stop"]["clean"] is False
    assert manifest["stop"]["failure_reasons"] == ["still alive"]
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
