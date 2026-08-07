#!/usr/bin/env python3
"""Record live stack ownership into a manifest (Windows process table + WSL snapshot)."""

from __future__ import annotations

import argparse
import json
import os
import subprocess
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from lifecycle.process_table import FakeProcessTable, ProcessInfo  # noqa: E402
from lifecycle.stack_manifest import load_manifest, save_manifest  # noqa: E402
from lifecycle.stack_ownership import (  # noqa: E402
    record_windows_processes,
    record_wsl_processes,
    set_ros_master,
    set_simulation_instance_id,
)


def _table_from_json(path: Path) -> FakeProcessTable:
    data = json.loads(path.read_text(encoding="utf-8-sig"))
    processes = [
        ProcessInfo(
            pid=int(item["pid"]),
            name=str(item.get("name", "")),
            start_time_utc=str(item.get("start_time_utc", "")),
            command_line=str(item.get("command_line", "")),
            parent_pid=int(item.get("parent_pid", 0)),
            pgid=item.get("pgid"),
        )
        for item in data
    ]
    return FakeProcessTable(processes)


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--manifest", required=True, type=Path)
    parser.add_argument("--distro", default="RflySim-20.04")
    parser.add_argument("--windows-json", type=Path, default=None)
    parser.add_argument("--wsl-snapshot-file", type=Path, default=None)
    args = parser.parse_args()

    manifest = load_manifest(args.manifest)

    if args.windows_json:
        win_table = _table_from_json(args.windows_json)
    else:
        from lifecycle.process_table import WindowsProcessTable

        win_table = WindowsProcessTable()
    record_windows_processes(
        manifest, win_table, launcher_pid=None, min_start_time_utc=manifest.get("start_time_utc")
    )

    if args.wsl_snapshot_file:
        lines = args.wsl_snapshot_file.read_text(encoding="utf-8").splitlines()
    else:
        ops_script = (
            f"/mnt/d/PX4PSP/RflySimAPIs/8.RflySimVision/3.CustExps/e13.RobotCom26Adv/"
            f"future_aircraft_sim/scripts/wsl/live_stack_wsl_ops.sh"
        )
        result = subprocess.run(
            ["wsl.exe", "-d", args.distro, "-e", "bash", "-lic", f"bash '{ops_script}' snapshot"],
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
            timeout=60,
        )
        lines = result.stdout.splitlines() if result.returncode == 0 else []
    record_wsl_processes(manifest, lines)

    if args.wsl_snapshot_file:
        set_simulation_instance_id(manifest, None)
    else:
        ops_script = (
            f"/mnt/d/PX4PSP/RflySimAPIs/8.RflySimVision/3.CustExps/e13.RobotCom26Adv/"
            f"future_aircraft_sim/scripts/wsl/live_stack_wsl_ops.sh"
        )
        result = subprocess.run(
            ["wsl.exe", "-d", args.distro, "-e", "bash", "-lic", f"bash '{ops_script}' sim-id"],
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
            timeout=60,
        )
        sim_id = result.stdout.strip() if result.returncode == 0 else None
        set_simulation_instance_id(manifest, sim_id)

    set_ros_master(manifest, os.environ.get("ROS_MASTER_URI", "http://127.0.0.1:11311"))
    save_manifest(manifest, args.manifest)
    print(
        f"[OK] recorded {len(manifest['windows_processes'])} windows / "
        f"{len(manifest['wsl_processes'])} wsl processes -> {args.manifest}"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
