#!/usr/bin/env python3
"""Run artifacts must emit a run-scoped provenance.json referenced by the flight report."""

from __future__ import annotations

import argparse
import hashlib
import importlib.util
import json
import re
import sys
import tempfile
from pathlib import Path


def load_module(name: str, module_path: Path):
    sys.path.insert(0, str(module_path.parent))
    spec = importlib.util.spec_from_file_location(name, str(module_path))
    if spec is None or spec.loader is None:
        raise RuntimeError(f"cannot load module: {module_path}")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def _write_course_spec(path: Path) -> None:
    path.write_text(
        json.dumps({"course_name": "predicted_narrow_course_v1", "base_map": "SLAMScene"}),
        encoding="utf-8",
    )


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--artifacts-module", required=True, type=Path)
    parser.add_argument("--report-module", required=True, type=Path)
    args = parser.parse_args()

    artifacts = load_module("stage7_run_artifacts", args.artifacts_module)
    report_module = load_module("stage7_flight_report", args.report_module)

    with tempfile.TemporaryDirectory() as temp_dir:
        output_dir = Path(temp_dir) / "run"
        course_path = Path(temp_dir) / "course.json"
        _write_course_spec(course_path)

        artifacts.begin_run(
            output_dir,
            "run-provenance-1",
            course_spec=course_path,
            simulation_instance_id="sim-42",
            ros_master_uri="http://127.0.0.1:11311",
        )
        provenance = json.loads((output_dir / "provenance.json").read_text(encoding="utf-8"))
        assert provenance["run_id"] == "run-provenance-1"
        assert provenance["stage"] == "stage7_live_slam_ego_swarm_flight"
        assert provenance["base_map"] == "SLAMScene", "base_map must come from the course spec"
        assert provenance["course_name"] == "predicted_narrow_course_v1"
        expected_sha = hashlib.sha256(course_path.read_bytes()).hexdigest()
        assert provenance["course_spec_sha256"] == expected_sha
        assert provenance["simulation_instance_id"] == "sim-42"
        assert provenance["ros_master_uri"] == "http://127.0.0.1:11311"
        commit = provenance["git_commit"]
        assert commit is None or re.fullmatch(r"[0-9a-f]{40}", commit) is not None, (
            "git_commit must be a full SHA or null when git is unavailable"
        )

        smoke_path = output_dir / "smoke.json"
        events_path = output_dir / "events.jsonl"
        trace_path = output_dir / "trace.json"
        score_path = output_dir / "score.json"
        executor_log = output_dir / "executor.log"
        smoke_path.write_text('{"ready": true}\n', encoding="utf-8")
        events_path.write_text(
            "".join(
                json.dumps({"time": i * 0.5, "event": name, "uav": "uav1"}) + "\n"
                for i, name in enumerate(
                    ("mission_start", "preflight_start", "preflight_success", "mission_end")
                )
            ),
            encoding="utf-8",
        )
        trace_path.write_text("[]\n", encoding="utf-8")
        score_path.write_text(
            json.dumps({"success": True, "failure_reasons": []}), encoding="utf-8"
        )
        executor_log.write_text("ok\n", encoding="utf-8")
        report = report_module.build_report(
            smoke_path,
            events_path,
            trace_path,
            score_path,
            executor_log,
            0,
            run_id="run-provenance-1",
            phase="complete",
            provenance_path=output_dir / "provenance.json",
        )
        assert report["provenance"]["run_id"] == "run-provenance-1"
        assert report["provenance"]["course_spec_sha256"] == expected_sha

    with tempfile.TemporaryDirectory() as temp_dir:
        output_dir = Path(temp_dir) / "run2"
        artifacts.begin_run(output_dir, "run-provenance-2", git_commit="0123456789abcdef0123456789abcdef01234567")
        provenance = json.loads((output_dir / "provenance.json").read_text(encoding="utf-8"))
        assert provenance["git_commit"] == "0123456789abcdef0123456789abcdef01234567"
        assert provenance["base_map"] is None

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
