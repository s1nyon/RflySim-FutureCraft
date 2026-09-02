#!/usr/bin/env python3
"""Start a Stage 7 live run with fail-closed, non-stale artifacts."""

from __future__ import annotations

import argparse
import hashlib
import json
import subprocess
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


def _git_commit():
    try:
        result = subprocess.run(
            ["git", "rev-parse", "HEAD"],
            capture_output=True,
            check=False,
            text=True,
            timeout=5,
        )
    except Exception:
        return None
    if result.returncode != 0:
        return None
    commit = result.stdout.strip()
    return commit if len(commit) == 40 else None


def _course_spec_sha256(course_spec):
    if course_spec is None:
        return None
    return hashlib.sha256(course_spec.read_bytes()).hexdigest()


def _course_meta(course_spec):
    if course_spec is None:
        return {}, None
    try:
        value = json.loads(course_spec.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError):
        return {}, None
    return {
        "course_name": value.get("course_name"),
        "base_map": value.get("base_map"),
    }, _course_spec_sha256(course_spec)


def begin_run(
    output_dir,
    run_id,
    *,
    git_commit=None,
    base_map=None,
    course_spec=None,
    simulation_instance_id=None,
    ros_master_uri=None,
):
    output_dir.mkdir(parents=True, exist_ok=True)
    for name in STALE_ARTIFACTS:
        path = output_dir / name
        if path.exists():
            path.unlink()
    if git_commit is None:
        git_commit = _git_commit()
    meta, course_sha = _course_meta(course_spec)
    if base_map is None:
        base_map = meta.get("base_map")
    provenance = {
        "stage": "stage7_live_slam_ego_swarm_flight",
        "run_id": run_id,
        "phase": "starting",
        "git_commit": git_commit,
        "base_map": base_map,
        "course_name": meta.get("course_name"),
        "course_spec": str(course_spec) if course_spec is not None else None,
        "course_spec_sha256": course_sha,
        "simulation_instance_id": simulation_instance_id,
        "ros_master_uri": ros_master_uri,
    }
    (output_dir / "provenance.json").write_text(
        json.dumps(provenance, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
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
    parser.add_argument("--git-commit", default=None)
    parser.add_argument("--base-map", default=None)
    parser.add_argument("--course-spec", type=Path, default=None)
    parser.add_argument("--simulation-instance-id", default=None)
    parser.add_argument("--ros-master-uri", default=None)
    args = parser.parse_args(argv)
    begin_run(
        args.output_dir,
        args.run_id,
        git_commit=args.git_commit,
        base_map=args.base_map,
        course_spec=args.course_spec,
        simulation_instance_id=args.simulation_instance_id,
        ros_master_uri=args.ros_master_uri,
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
