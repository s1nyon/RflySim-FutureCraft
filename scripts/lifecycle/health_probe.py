#!/usr/bin/env python3
"""CLI for the stack health gate: per-status atomic writes and fail-closed aggregation."""

from __future__ import annotations

import argparse
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from lifecycle.health_gate import (  # noqa: E402
    all_ready,
    health_summary,
    write_status_file,
)


def main() -> int:
    parser = argparse.ArgumentParser()
    sub = parser.add_subparsers(dest="cmd", required=True)

    write = sub.add_parser("write")
    write.add_argument("--health-dir", required=True, type=Path)
    write.add_argument("--stack-id", required=True)
    write.add_argument("--status", required=True)
    write.add_argument("--ready", choices=["true", "false"], required=True)
    write.add_argument("--detail", default="")

    check = sub.add_parser("check")
    check.add_argument("--health-dir", required=True, type=Path)
    check.add_argument("--wait-seconds", type=int, default=0)

    args = parser.parse_args()
    health_dir = args.health_dir.resolve()

    if args.cmd == "write":
        write_status_file(health_dir, args.stack_id, args.status, args.ready == "true", args.detail)
        print(f"[health] {health_summary(health_dir)}")
        return 0

    if args.cmd == "check":
        deadline = time.time() + max(0, args.wait_seconds)
        while True:
            if all_ready(health_dir):
                print(f"[PASS] {health_summary(health_dir)}")
                return 0
            print(f"[WAIT] {health_summary(health_dir)}")
            if args.wait_seconds <= 0 or time.time() >= deadline:
                break
            time.sleep(5)
        print(f"[FAIL] health gate not ready (waited {args.wait_seconds}s)")
        return 1

    return 2


if __name__ == "__main__":
    raise SystemExit(main())
