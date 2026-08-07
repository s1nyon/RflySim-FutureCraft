#!/usr/bin/env python3
"""CLI for the stack health gate: merge status writes and all-ready checks (fail closed)."""

from __future__ import annotations

import argparse
import json
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from lifecycle.health_gate import (  # noqa: E402
    all_ready,
    health_summary,
    load_health,
    merge_status,
    new_health,
    save_health,
)


def _load_or_new(health_dir: Path, stack_id: str) -> dict:
    path = health_dir / "health.json"
    if path.exists():
        try:
            return load_health(path)
        except (ValueError, json.JSONDecodeError):
            return new_health(stack_id)
    return new_health(stack_id)


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
        health = _load_or_new(health_dir, args.stack_id)
        merge_status(health, args.status, ready=args.ready == "true", detail=args.detail)
        save_health(health, health_dir / "health.json")
        print(f"[health] {health_summary(health)}")
        return 0

    if args.cmd == "check":
        path = health_dir / "health.json"
        deadline = time.time() + max(0, args.wait_seconds)
        while True:
            if path.exists():
                try:
                    health = load_health(path)
                    if all_ready(health):
                        print(f"[PASS] {health_summary(health)}")
                        return 0
                    print(f"[WAIT] {health_summary(health)}")
                except (ValueError, json.JSONDecodeError) as exc:
                    print(f"[WAIT] invalid health file: {exc}")
            else:
                print(f"[WAIT] health.json not found: {path}")
            if args.wait_seconds <= 0 or time.time() >= deadline:
                break
            time.sleep(5)
        print(f"[FAIL] health gate not ready (waited {args.wait_seconds}s)")
        return 1

    return 2


if __name__ == "__main__":
    raise SystemExit(main())
