#!/usr/bin/env python3
"""Validate the compact, tracked PBL-1 evidence snapshots."""

from __future__ import annotations

import argparse
import json
import re
import subprocess
import sys
import tempfile
from pathlib import Path
from typing import Any


APPROVED_RUN_IDS = (
    "stage7-20260807T133813Z-2617",
    "stage7-20260807T134731Z-2508",
    "stage7-20260807T141751Z-3219",
)
REQUIRED = {
    "sensor_readiness.json",
    "flight_report.json",
    "score_summary.json",
    "provenance.json",
    "executor_trace.json",
    "mission_events.jsonl",
    "slam_ego_swarm_smoke_report.json",
}
COURSE_SPEC = "config/maps/predicted_narrow_course_v1.json"
PYTHON = Path(r"D:\PX4PSP\Python38\python.exe")
MACHINE_SPECIFIC = re.compile(
    r"(?:(?<![a-z0-9])[a-z]:[\\/]|/mnt/[a-z]/|PC-202|Administrator)", re.IGNORECASE
)


def load_json(path: Path) -> Any:
    with path.open("r", encoding="utf-8") as stream:
        return json.load(stream)


def check_output_root(output_root: Path) -> None:
    children = {path.name: path for path in output_root.iterdir()}
    assert set(children) == set(APPROVED_RUN_IDS), (
        "curated run directories differ: "
        f"missing={sorted(set(APPROVED_RUN_IDS) - set(children))} "
        f"unexpected={sorted(set(children) - set(APPROVED_RUN_IDS))}"
    )
    for run_id, path in children.items():
        assert path.is_dir() and not path.is_symlink(), (
            f"invalid curated run directory: {run_id}"
        )


def check_run(output_root: Path, run_id: str) -> None:
    run_directory = output_root / run_id
    assert run_directory.is_dir(), f"missing curated evidence directory: {run_directory}"
    assert not run_directory.is_symlink(), f"curated evidence directory is a symlink: {run_directory}"

    names = {path.name for path in run_directory.iterdir()}
    assert names == REQUIRED, (
        f"curated evidence files differ for {run_id}: "
        f"missing={sorted(REQUIRED - names)} unexpected={sorted(names - REQUIRED)}"
    )
    for name in REQUIRED:
        path = run_directory / name
        assert path.is_file() and not path.is_symlink(), f"invalid curated evidence file: {path}"
        assert not MACHINE_SPECIFIC.search(path.read_text(encoding="utf-8")), (
            f"machine-specific content remains in curated evidence: {path}"
        )

    score = load_json(run_directory / "score_summary.json")
    assert score.get("success") is True, f"PBL-1 score is not successful: {run_id}"

    readiness = load_json(run_directory / "sensor_readiness.json")
    assert readiness.get("errors") == [], f"sensor readiness has errors: {run_id}"

    flight_report = load_json(run_directory / "flight_report.json")
    checks = flight_report.get("checks", {})
    for confirmation in ("arming_confirmed", "navigation_confirmed", "landing_confirmed"):
        vehicles = checks.get(confirmation, {})
        for vehicle in ("uav1", "uav2"):
            assert vehicles.get(vehicle) is True, (
                f"{confirmation} is not true for {vehicle}: {run_id}"
            )

    provenance = load_json(run_directory / "provenance.json")
    assert provenance.get("run_id") == run_id, f"provenance run_id mismatch: {run_id}"
    assert provenance.get("course_spec") == COURSE_SPEC, (
        f"provenance course_spec is not repository-relative: {run_id}"
    )

    for line_number, line in enumerate(
        (run_directory / "mission_events.jsonl").read_text(encoding="utf-8").splitlines(),
        start=1,
    ):
        assert line.strip(), f"blank mission event at {run_id}:{line_number}"
        json.loads(line)


def write_source_run(logs_root: Path, run_id: str) -> dict[str, bytes]:
    run_directory = logs_root / run_id
    run_directory.mkdir(parents=True)
    project_root = logs_root.parent.parent.resolve()
    rooted_artifact = project_root / "logs" / "stage7_live" / run_id / "executor_trace.json"
    drive = project_root.drive.rstrip(":").lower()
    wsl_project_root = f"/mnt/{drive}/{project_root.as_posix().split(':', 1)[1].lstrip('/')}"
    payloads = {
        "sensor_readiness.json": {"run_id": run_id, "errors": [], "ready": True},
        "flight_report.json": {
            "run_id": run_id,
            "paths": {
                "windows": str(rooted_artifact),
                "wsl": f"{wsl_project_root}/logs/stage7_live/{run_id}/executor_trace.json",
                "non_rooted": "relative/original-value.json",
            },
            "provenance": {
                "course_spec": f"{wsl_project_root}/config/maps/predicted_narrow_course_v1.json"
            },
            "checks": {
                "arming_confirmed": {"uav1": True, "uav2": True},
                "navigation_confirmed": {"uav1": True, "uav2": True},
                "landing_confirmed": {"uav1": True, "uav2": True},
            },
        },
        "score_summary.json": {"success": True, "failure_reasons": []},
        "provenance.json": {
            "run_id": run_id,
            "course_spec": r"D:\machine-specific\predicted_narrow_course_v1.json",
            "untouched": {"value": 7},
        },
        "executor_trace.json": {"events": [{"event": "complete"}]},
        "slam_ego_swarm_smoke_report.json": {"ready": True},
    }
    written: dict[str, bytes] = {}
    for name, payload in payloads.items():
        content = (json.dumps(payload, indent=2) + "\n").encode("utf-8")
        (run_directory / name).write_bytes(content)
        written[name] = content
    mission_events = (
        json.dumps(
            {
                "event": "armed",
                "artifacts": [
                    str(rooted_artifact),
                    f"{wsl_project_root}/logs/stage7_live/{run_id}/executor_trace.json",
                    "relative/original-value.json",
                ],
            }
        )
        + "\n"
        + json.dumps({"event": "landed", "sequence": 2})
        + "\n"
    ).encode("utf-8")
    (run_directory / "mission_events.jsonl").write_bytes(mission_events)
    written["mission_events.jsonl"] = mission_events
    (run_directory / "large-runtime.log").write_text("must not be copied", encoding="utf-8")
    return written


def run_curator(script: Path, logs_root: Path, output_root: Path) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        [
            str(PYTHON),
            str(script),
            "--logs-root",
            str(logs_root),
            "--output-root",
            str(output_root),
        ],
        text=True,
        capture_output=True,
        timeout=30,
        check=False,
    )


def snapshot_output_bytes(output_root: Path) -> dict[str, bytes]:
    return {
        path.relative_to(output_root).as_posix(): path.read_bytes()
        for path in output_root.rglob("*")
        if path.is_file()
    }


def check_curator_contract(project_root: Path) -> None:
    script = project_root / "scripts" / "maintenance" / "curate_pbl1_evidence.py"
    with tempfile.TemporaryDirectory(prefix="pbl1-curator-") as directory:
        fixture = Path(directory)
        logs_root = fixture / "logs" / "stage7_live"
        output_root = fixture / "docs" / "evidence" / "pbl1"
        originals = {
            run_id: write_source_run(logs_root, run_id) for run_id in APPROVED_RUN_IDS
        }
        result = run_curator(script, logs_root, output_root)
        assert result.returncode == 0, result.stdout + result.stderr
        check_output_root(output_root)
        for run_id in APPROVED_RUN_IDS:
            check_run(output_root, run_id)
            curated = output_root / run_id
            assert not (curated / "large-runtime.log").exists(), "curator copied a .log file"
            for name in REQUIRED - {
                "provenance.json",
                "flight_report.json",
                "mission_events.jsonl",
            }:
                assert (curated / name).read_bytes() == originals[run_id][name], (
                    f"curator changed source content: {run_id}/{name}"
                )
            source_provenance = json.loads(originals[run_id]["provenance.json"])
            curated_provenance = load_json(curated / "provenance.json")
            source_provenance["course_spec"] = COURSE_SPEC
            assert curated_provenance == source_provenance, (
                f"curator changed provenance fields other than course_spec: {run_id}"
            )
            curated_flight = load_json(curated / "flight_report.json")
            expected_artifact = f"logs/stage7_live/{run_id}/executor_trace.json"
            expected_flight = json.loads(originals[run_id]["flight_report.json"])
            expected_flight["paths"] = {
                "windows": expected_artifact,
                "wsl": expected_artifact,
                "non_rooted": "relative/original-value.json",
            }
            expected_flight["provenance"]["course_spec"] = COURSE_SPEC
            assert curated_flight == expected_flight, (
                f"curator did not normalize only canonical-rooted paths: {run_id}"
            )
            curated_events = [
                json.loads(line)
                for line in (curated / "mission_events.jsonl")
                .read_text(encoding="utf-8")
                .splitlines()
            ]
            assert curated_events == [
                {
                    "event": "armed",
                    "artifacts": [
                        expected_artifact,
                        expected_artifact,
                        "relative/original-value.json",
                    ],
                },
                {"event": "landed", "sequence": 2},
            ], f"curator changed JSONL record/key order or non-root values: {run_id}"

    with tempfile.TemporaryDirectory(prefix="pbl1-curator-unexpected-output-") as directory:
        fixture = Path(directory)
        logs_root = fixture / "logs" / "stage7_live"
        output_root = fixture / "docs" / "evidence" / "pbl1"
        for run_id in APPROVED_RUN_IDS:
            write_source_run(logs_root, run_id)
        unexpected = output_root / "unapproved-run"
        unexpected.mkdir(parents=True)
        marker = unexpected / "preserve.txt"
        marker.write_text("untouched", encoding="utf-8")
        result = run_curator(script, logs_root, output_root)
        assert result.returncode != 0, "curator accepted an unapproved output run"
        assert {path.name for path in output_root.iterdir()} == {"unapproved-run"}, (
            "curator wrote partial output before rejecting an unapproved run"
        )
        assert marker.read_text(encoding="utf-8") == "untouched"

    with tempfile.TemporaryDirectory(prefix="pbl1-curator-late-invalid-run-") as directory:
        fixture = Path(directory)
        logs_root = fixture / "logs" / "stage7_live"
        output_root = fixture / "docs" / "evidence" / "pbl1"
        for run_id in APPROVED_RUN_IDS:
            write_source_run(logs_root, run_id)
            destination_run = output_root / run_id
            destination_run.mkdir(parents=True)
            for name in REQUIRED:
                (destination_run / name).write_bytes(
                    f"sentinel:{run_id}:{name}".encode("utf-8")
                )
        (output_root / APPROVED_RUN_IDS[1] / "unexpected.txt").write_bytes(
            b"must remain untouched"
        )
        before = snapshot_output_bytes(output_root)
        result = run_curator(script, logs_root, output_root)
        assert result.returncode != 0, "curator accepted an unexpected file in a later run"
        after = snapshot_output_bytes(output_root)
        assert after == before, "curator modified output before completing all-run preflight"

    for case, mutation in (
        ("failed-score", lambda root: (root / APPROVED_RUN_IDS[0] / "score_summary.json").write_text(
            json.dumps({"success": False}), encoding="utf-8"
        )),
        ("readiness-error", lambda root: (root / APPROVED_RUN_IDS[0] / "sensor_readiness.json").write_text(
            json.dumps({"errors": ["not ready"]}), encoding="utf-8"
        )),
        ("residual-machine-id", lambda root: (root / APPROVED_RUN_IDS[0] / "executor_trace.json").write_text(
            json.dumps({"operator": "Administrator"}), encoding="utf-8"
        )),
    ):
        with tempfile.TemporaryDirectory(prefix=f"pbl1-curator-{case}-") as directory:
            fixture = Path(directory)
            logs_root = fixture / "logs" / "stage7_live"
            output_root = fixture / "docs" / "evidence" / "pbl1"
            for run_id in APPROVED_RUN_IDS:
                write_source_run(logs_root, run_id)
            mutation(logs_root)
            result = run_curator(script, logs_root, output_root)
            assert result.returncode != 0, f"curator accepted {case}"
            assert not output_root.exists(), f"curator left partial output for {case}"

    with tempfile.TemporaryDirectory(prefix="pbl1-curator-symlink-") as directory:
        fixture = Path(directory)
        logs_root = fixture / "logs" / "stage7_live"
        output_root = fixture / "docs" / "evidence" / "pbl1"
        for run_id in APPROVED_RUN_IDS:
            write_source_run(logs_root, run_id)
        source = logs_root / APPROVED_RUN_IDS[0] / "executor_trace.json"
        target = source.with_suffix(".target")
        source.replace(target)
        source.symlink_to(target)
        result = run_curator(script, logs_root, output_root)
        assert result.returncode != 0, "curator accepted a source symlink"
        assert not output_root.exists(), "curator left partial output after symlink rejection"


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--project-root", required=True, type=Path)
    args = parser.parse_args()
    output_root = args.project_root.resolve() / "docs" / "evidence" / "pbl1"

    try:
        check_curator_contract(args.project_root.resolve())
        check_output_root(output_root)
        for run_id in APPROVED_RUN_IDS:
            check_run(output_root, run_id)
    except (AssertionError, OSError, json.JSONDecodeError, subprocess.TimeoutExpired) as exc:
        print(f"[FAIL] PBL-1 evidence snapshots: {exc}", file=sys.stderr)
        return 1

    print("[PASS] PBL-1 evidence snapshots")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
