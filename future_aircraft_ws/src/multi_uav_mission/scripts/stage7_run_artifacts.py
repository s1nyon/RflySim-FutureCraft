#!/usr/bin/env python3
"""Start a Stage 7 live run with fail-closed, non-stale artifacts."""

from __future__ import annotations

import argparse
import json
from pathlib import Path


STALE_ARTIFACTS = (
    "mission_events.jsonl",
    "executor_trace.json",
    "score_summary.json",
    "executor.log",
    "slam_ego_swarm_smoke_report.json",
    "live_slam_ego_swarm_plan.json",
    "runner.log",
)


def begin_run(output_dir, run_id):
    output_dir.mkdir(parents=True, exist_ok=True)
    for name in STALE_ARTIFACTS:
        path = output_dir / name
        if path.exists():
            path.unlink()
    report = {
        "stage": "stage7_live_slam_ego_swarm_flight",
        "run_id": run_id,
        "phase": "starting",
        "ready": False,
    }
    (output_dir / "flight_report.json").write_text(
        json.dumps(report, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    return report


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output-dir", required=True, type=Path)
    parser.add_argument("--run-id", required=True)
    args = parser.parse_args(argv)
    begin_run(args.output_dir, args.run_id)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
