#!/usr/bin/env python3
"""Dual-UAV topology invariant:
- one CopterSim only            -> NOT READY
- two CopterSim entries same PID -> NOT READY
- missing/dead PX4 uav2          -> NOT READY
- stale (PID reuse) CopterSim    -> NOT READY
- correct dual topology          -> READY
"""

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
    parser.add_argument("--topology-module", required=True, type=Path)
    parser.add_argument("--process-table-module", required=True, type=Path)
    parser.add_argument("--manifest-module", required=True, type=Path)
    parser.add_argument("--ownership-module", required=True, type=Path)
    args = parser.parse_args()

    topology = load_module("stack_topology", args.topology_module)
    table_mod = load_module("process_table", args.process_table_module)
    manifest_mod = load_module("stack_manifest", args.manifest_module)
    ownership = load_module("stack_ownership", args.ownership_module)

    STACK = "stack-20260808T120000Z-a1b2c3d4"

    def build_manifest(copter_uav2_role="gui:CopterSim/uav2"):
        manifest = manifest_mod.new_manifest(
            stack_id=STACK, launcher={"kind": "batch", "identity": "test"}
        )
        ownership.register_process(
            manifest, side="windows", pid=1001, role="gui:CopterSim/uav1", name="CopterSim",
            command_line='"D:\\PX4PSP\\CopterSim\\CopterSim.exe" 1 1 310 0 2 SLAMScene 0 -0.7 16 90 1 Mavlink_Vision',
            start_time_utc="2026-08-08T12:00:05Z", reason="t",
        )
        ownership.register_process(
            manifest, side="windows", pid=1002, role=copter_uav2_role, name="CopterSim",
            command_line='"D:\\PX4PSP\\CopterSim\\CopterSim.exe" 1 2 310 0 2 SLAMScene 0 0.7 16 90 1 Mavlink_Vision',
            start_time_utc="2026-08-08T12:00:08Z", reason="t",
        )
        ownership.register_process(
            manifest, side="wsl", pid=2001, pgid=2000, role="wsl:px4_uav1", name="px4",
            command_line="../bin/px4 -i 1 -d /mnt/d/PX4PSP/Firmware/build/px4_sitl_default/etc -s etc/init.d-posix/rcS",
            start_time_utc="2026-08-08T12:00:20Z", reason="t",
        )
        ownership.register_process(
            manifest, side="wsl", pid=2002, pgid=2000, role="wsl:px4_uav2", name="px4",
            command_line="../bin/px4 -i 2 -d /mnt/d/PX4PSP/Firmware/build/px4_sitl_default/etc -s etc/init.d-posix/rcS",
            start_time_utc="2026-08-08T12:00:23Z", reason="t",
        )
        ownership.register_process(
            manifest, side="wsl", pid=2003, pgid=2000, role="wsl:px4_uav2:px4-simulator", name="px4",
            command_line="px4-simulator --instance 2 start -c 4561",
            start_time_utc="2026-08-08T12:00:24Z", reason="t",
        )
        return manifest

    def win(c1, c2):
        return table_mod.FakeProcessTable(
            [
                table_mod.ProcessInfo(
                    pid=1001, name="CopterSim", start_time_utc="2026-08-08T12:00:05Z",
                    command_line='"D:\\PX4PSP\\CopterSim\\CopterSim.exe" 1 1 310 0 2 SLAMScene 0 -0.7 16 90 1 Mavlink_Vision',
                    parent_pid=900,
                ),
                c1,
                c2,
            ]
        )

    def wsl_table(px4s):
        return table_mod.FakeProcessTable(px4s)

    px4_1 = table_mod.ProcessInfo(
        pid=2001, name="px4", start_time_utc="2026-08-08T12:00:20Z",
        command_line="../bin/px4 -i 1 -d /mnt/d/PX4PSP/Firmware/build/px4_sitl_default/etc -s etc/init.d-posix/rcS",
        parent_pid=1999, pgid=2000,
    )
    px4_2 = table_mod.ProcessInfo(
        pid=2002, name="px4", start_time_utc="2026-08-08T12:00:23Z",
        command_line="../bin/px4 -i 2 -d /mnt/d/PX4PSP/Firmware/build/px4_sitl_default/etc -s etc/init.d-posix/rcS",
        parent_pid=1999, pgid=2000,
    )
    px4_sim = table_mod.ProcessInfo(
        pid=2003, name="px4", start_time_utc="2026-08-08T12:00:24Z",
        command_line="px4-simulator --instance 2 start -c 4561",
        parent_pid=1999, pgid=2000,
    )

    def copter2(pid=1002, start="2026-08-08T12:00:08Z", cmd=None):
        cmd = cmd or '"D:\\PX4PSP\\CopterSim\\CopterSim.exe" 1 2 310 0 2 SLAMScene 0 0.7 16 90 1 Mavlink_Vision'
        return table_mod.ProcessInfo(
            pid=pid, name="CopterSim", start_time_utc=start, command_line=cmd, parent_pid=900,
        )

    # 1. Correct dual topology -> READY.
    m = build_manifest()
    report = topology.check_topology(
        m,
        win_table=win(copter2(), None),
        wsl_table=wsl_table([px4_1, px4_2, px4_sim]),
    )
    assert report.ready is True, f"dual topology must be ready: {report.reasons}"

    # 2. Only one CopterSim registered -> NOT READY.
    m = build_manifest()
    m["windows_processes"] = [e for e in m["windows_processes"] if e["role"] != "gui:CopterSim/uav2"]
    report = topology.check_topology(m, win_table=win(copter2(), None), wsl_table=wsl_table([px4_1, px4_2]))
    assert report.ready is False and any("CopterSim uav2" in r for r in report.reasons)

    # 3. Two CopterSim entries share the same PID -> NOT READY.
    m = build_manifest()
    m["windows_processes"][1]["pid"] = 1001
    report = topology.check_topology(m, win_table=win(copter2(), None), wsl_table=wsl_table([px4_1, px4_2]))
    assert report.ready is False and any("duplicate PID" in r for r in report.reasons)

    # 4. CopterSim uav2 dead (PID missing from process table) -> NOT READY.
    m = build_manifest()
    report = topology.check_topology(
        m,
        win_table=table_mod.FakeProcessTable(
            [
                table_mod.ProcessInfo(
                    pid=1001, name="CopterSim", start_time_utc="2026-08-08T12:00:05Z",
                    command_line='"D:\\PX4PSP\\CopterSim\\CopterSim.exe" 1 1 310 0 2 SLAMScene 0 -0.7 16 90 1 Mavlink_Vision',
                    parent_pid=900,
                )
            ]
        ),
        wsl_table=wsl_table([px4_1, px4_2]),
    )
    assert report.ready is False and any("CopterSim uav2" in r for r in report.reasons)

    # 5. Stale (PID reused, start time differs) CopterSim uav1 -> NOT READY.
    m = build_manifest()
    report = topology.check_topology(
        m,
        win_table=win(copter2(start="2026-08-08T14:00:00Z"), None),
        wsl_table=wsl_table([px4_1, px4_2]),
    )
    assert report.ready is False and any("stale" in r for r in report.reasons)

    # 6. PX4 uav2 missing from manifest -> NOT READY.
    m = build_manifest()
    m["wsl_processes"] = [e for e in m["wsl_processes"] if e["role"] != "wsl:px4_uav2"]
    report = topology.check_topology(m, win_table=win(copter2(), None), wsl_table=wsl_table([px4_1]))
    assert report.ready is False and any("PX4 uav2" in r for r in report.reasons)

    # 7. PX4 uav1 stale (reused PID) -> NOT READY.
    m = build_manifest()
    stale_px4 = table_mod.ProcessInfo(
        pid=2001, name="px4", start_time_utc="2026-08-08T15:00:00Z",
        command_line="../bin/px4 -i 1 -d /mnt/d/PX4PSP/Firmware/build/px4_sitl_default/etc -s etc/init.d-posix/rcS",
        parent_pid=1, pgid=2000,
    )
    report = topology.check_topology(
        m, win_table=win(copter2(), None), wsl_table=wsl_table([stale_px4, px4_2])
    )
    assert report.ready is False and any("PX4 uav1" in r for r in report.reasons)

    # 8. Evidence JSON serializable and carries instance readiness semantics.
    m = build_manifest()
    report = topology.check_topology(m, win_table=win(copter2(), None), wsl_table=wsl_table([px4_1, px4_2, px4_sim]))
    payload = json.loads(json.dumps(topology.report_to_dict(report)))
    assert payload["evidence"]["CopterSim_uav1"]["ready"] is True
    assert payload["evidence"]["CopterSim_uav2"]["ready"] is True
    assert payload["evidence"]["PX4_uav1"]["ready"] is True
    assert payload["evidence"]["PX4_uav2"]["ready"] is True

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
