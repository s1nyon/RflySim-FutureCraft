#!/usr/bin/env python3
"""Registration-at-creation CLI: the ONLY way entries gain ownership in a stack manifest."""

from __future__ import annotations

import argparse
import os
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from lifecycle.stack_manifest import load_manifest, save_manifest  # noqa: E402
from lifecycle.stack_ownership import (  # noqa: E402
    register_process,
    set_ros_master,
    set_simulation_instance_id,
)


def _load_save(args) -> dict:
    manifest = load_manifest(args.manifest)
    try:
        if args.cmd == "register":
            entry = register_process(
                manifest,
                side=args.side,
                pid=args.pid,
                role=args.role,
                name=args.name,
                command_line=args.cmdline,
                start_time_utc=args.start_time,
                pgid=args.pgid,
                reason=args.reason,
            )
            print(
                f"[OK] registered side={args.side} pid={entry['pid']} pgid={entry.get('pgid')} "
                f"role={entry['role']} -> {args.manifest}"
            )
        elif args.cmd == "set-sim-id":
            set_simulation_instance_id(manifest, args.simulation_instance_id)
            print(f"[OK] simulation_instance_id={args.simulation_instance_id}")
        elif args.cmd == "set-ros-master":
            set_ros_master(manifest, args.uri)
            print(f"[OK] ros_master={args.uri}")
        else:
            raise SystemExit(2)
        save_manifest(manifest, args.manifest)
    except ValueError as exc:
        print(f"[ERROR] {exc}", file=sys.stderr)
        return 1
    return 0


def main() -> int:
    parser = argparse.ArgumentParser()
    sub = parser.add_subparsers(dest="cmd", required=True)

    reg = sub.add_parser("register")
    reg.add_argument("--manifest", required=True, type=Path)
    reg.add_argument("--side", required=True, choices=("windows", "wsl"))
    reg.add_argument("--pid", required=True, type=int)
    reg.add_argument("--pgid", type=int, default=None)
    reg.add_argument("--role", required=True)
    reg.add_argument("--name", default="")
    reg.add_argument("--cmdline", required=True)
    reg.add_argument("--start-time", default=None)
    reg.add_argument("--reason", required=True)

    sim = sub.add_parser("set-sim-id")
    sim.add_argument("--manifest", required=True, type=Path)
    sim.add_argument("--simulation-instance-id", required=True)

    ros = sub.add_parser("set-ros-master")
    ros.add_argument("--manifest", required=True, type=Path)
    ros.add_argument("--uri", default=os.environ.get("ROS_MASTER_URI", "http://127.0.0.1:11311"))

    args = parser.parse_args()
    return _load_save(args)


if __name__ == "__main__":
    raise SystemExit(main())
