#!/usr/bin/env python3
"""CLI for the stack health gate: per-status atomic writes and fail-closed aggregation."""

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
    write_status_file,
)


def topology_ready(manifest_path: Path, distro: str = "RflySim-20.04") -> tuple:
    """Enforce the dual-UAV topology invariant on top of the per-status gate.

    Returns (ready, report_dict). Requires CopterSim uav1/uav2 and PX4 uav1/uav2
    to be exactly the owned, alive, identity-matching instances of THIS stack.
    """
    from lifecycle.process_table import WindowsProcessTable, WslProcessTable  # noqa: E402
    from lifecycle.stack_manifest import load_manifest  # noqa: E402
    from lifecycle.stack_topology import check_topology, report_to_dict  # noqa: E402

    manifest = load_manifest(manifest_path)
    report = check_topology(manifest, WindowsProcessTable(), WslProcessTable(distro))
    payload = report_to_dict(report)
    stack_dir = manifest_path.resolve().parent
    try:
        (stack_dir / "topology_report.json").write_text(
            json.dumps(payload, indent=2, ensure_ascii=False) + "\n",
            encoding="utf-8",
        )
    except OSError:
        pass
    return report.ready, payload


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
    check.add_argument("--manifest", type=Path, default=None)
    check.add_argument("--distro", default="RflySim-20.04")

    args = parser.parse_args()
    health_dir = args.health_dir.resolve()

    if args.cmd == "write":
        write_status_file(health_dir, args.stack_id, args.status, args.ready == "true", args.detail)
        print(f"[health] {health_summary(health_dir)}")
        return 0

    if args.cmd == "check":
        deadline = time.time() + max(0, args.wait_seconds)
        while True:
            statuses_ok = all_ready(health_dir)
            topo_ok = True
            topo_payload = None
            topo_note = ""
            if statuses_ok and args.manifest is not None:
                topo_ok, topo_payload = topology_ready(args.manifest, args.distro)
                if not topo_ok:
                    topo_note = " TOPOLOGY_NOT_READY"
            if statuses_ok and topo_ok:
                print(f"[PASS] {health_summary(health_dir)} TOPOLOGY_READY")
                if topo_payload:
                    print("[TOPOLOGY] " + json.dumps(topo_payload.get("evidence", {}), ensure_ascii=False))
                return 0
            print(f"[WAIT] {health_summary(health_dir)}{topo_note}")
            if args.wait_seconds <= 0 or time.time() >= deadline:
                break
            time.sleep(5)
        print(f"[FAIL] health gate not ready (waited {args.wait_seconds}s)")
        if args.manifest is not None and args.wait_seconds <= 0:
            statuses_ok = all_ready(health_dir)
            if statuses_ok:
                _, topo_payload = topology_ready(args.manifest, args.distro)
                print("[TOPOLOGY] " + json.dumps(topo_payload, ensure_ascii=False, indent=2))
        return 1

    return 2


if __name__ == "__main__":
    raise SystemExit(main())
