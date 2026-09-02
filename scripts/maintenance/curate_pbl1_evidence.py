#!/usr/bin/env python3
"""Create compact, deterministic snapshots of the three approved PBL-1 runs."""

from __future__ import annotations

import argparse
import json
import os
import re
import sys
from pathlib import Path
from typing import Any


APPROVED_RUN_IDS = (
    "stage7-20260807T133813Z-2617",
    "stage7-20260807T134731Z-2508",
    "stage7-20260807T141751Z-3219",
)
ALLOWED_FILES = (
    "sensor_readiness.json",
    "flight_report.json",
    "score_summary.json",
    "provenance.json",
    "executor_trace.json",
    "mission_events.jsonl",
    "slam_ego_swarm_smoke_report.json",
)
COURSE_SPEC = "config/maps/predicted_narrow_course_v1.json"
MACHINE_SPECIFIC = re.compile(
    r"(?:(?<![a-z0-9])[a-z]:[\\/]|/mnt/[a-z]/|PC-202|Administrator)", re.IGNORECASE
)


def is_contained(path: Path, root: Path) -> bool:
    return os.path.commonpath((str(path), str(root))) == str(root)


def load_json(path: Path) -> Any:
    with path.open("r", encoding="utf-8") as stream:
        return json.load(stream)


def validate_jsonl(path: Path) -> list[Any]:
    records = []
    with path.open("r", encoding="utf-8") as stream:
        for line_number, line in enumerate(stream, start=1):
            if not line.strip():
                raise ValueError(f"blank JSONL record: {path}:{line_number}")
            records.append(json.loads(line))
    return records


def validate_source_run(logs_root: Path, run_id: str) -> dict[str, Any]:
    run_candidate = logs_root / run_id
    if run_candidate.is_symlink():
        raise ValueError(f"source run is a symlink: {run_candidate}")
    run_directory = run_candidate.resolve(strict=True)
    if not run_directory.is_dir() or not is_contained(run_directory, logs_root):
        raise ValueError(f"source run escapes logs root: {run_candidate} -> {run_directory}")
    for child in run_directory.iterdir():
        if child.is_symlink():
            raise ValueError(f"unexpected source symlink: {child}")

    parsed: dict[str, Any] = {}
    for name in ALLOWED_FILES:
        source = run_directory / name
        if source.is_symlink() or not source.is_file():
            raise ValueError(f"missing or linked source evidence: {source}")
        resolved_source = source.resolve(strict=True)
        if not is_contained(resolved_source, run_directory):
            raise ValueError(f"source evidence escapes run directory: {source}")
        if name.endswith(".json"):
            parsed[name] = load_json(source)
        else:
            parsed[name] = validate_jsonl(source)

    if parsed["score_summary.json"].get("success") is not True:
        raise ValueError(f"approved run has a failed score: {run_id}")
    if parsed["sensor_readiness.json"].get("errors") != []:
        raise ValueError(f"approved run has readiness errors: {run_id}")
    if parsed["provenance.json"].get("run_id") != run_id:
        raise ValueError(f"approved run has mismatched provenance: {run_id}")
    return parsed


def project_path_roots(project_root: Path) -> tuple[str, ...]:
    windows_root = str(project_root)
    forward_root = project_root.as_posix()
    roots = [windows_root, forward_root]
    drive = project_root.drive.rstrip(":")
    if drive:
        suffix = forward_root.split(":", 1)[1].lstrip("/")
        roots.append(f"/mnt/{drive.lower()}/{suffix}")
    return tuple(dict.fromkeys(root.rstrip("/\\") for root in roots))


def normalize_rooted_value(value: Any, roots: tuple[str, ...]) -> Any:
    if isinstance(value, dict):
        return {key: normalize_rooted_value(child, roots) for key, child in value.items()}
    if isinstance(value, list):
        return [normalize_rooted_value(child, roots) for child in value]
    if not isinstance(value, str):
        return value
    folded_value = value.casefold()
    for root in sorted(roots, key=len, reverse=True):
        folded_root = root.casefold()
        if folded_value == folded_root:
            return "."
        for separator in ("/", "\\"):
            prefix = folded_root + separator
            if folded_value.startswith(prefix):
                return value[len(root) + 1 :].replace("\\", "/")
    return value


def assert_portable(value: Any, location: str) -> None:
    if isinstance(value, dict):
        for key, child in value.items():
            if MACHINE_SPECIFIC.search(str(key)):
                raise ValueError(f"machine-specific key remains in {location}: {key}")
            assert_portable(child, location)
    elif isinstance(value, list):
        for child in value:
            assert_portable(child, location)
    elif isinstance(value, str) and MACHINE_SPECIFIC.search(value):
        raise ValueError(f"machine-specific value remains in {location}: {value}")


def prepare_output(
    logs_root: Path,
    project_root: Path,
    parsed_runs: dict[str, dict[str, Any]],
) -> dict[str, dict[str, bytes]]:
    roots = project_path_roots(project_root)
    prepared: dict[str, dict[str, bytes]] = {}
    for run_id in APPROVED_RUN_IDS:
        prepared[run_id] = {}
        for name in ALLOWED_FILES:
            source = logs_root / run_id / name
            original = parsed_runs[run_id][name]
            transformed = normalize_rooted_value(original, roots)
            if name == "provenance.json":
                transformed = dict(transformed)
                transformed["course_spec"] = COURSE_SPEC
            assert_portable(transformed, f"{run_id}/{name}")
            if transformed == original:
                content = source.read_bytes()
            elif name.endswith(".json"):
                content = (
                    json.dumps(transformed, indent=2, ensure_ascii=False) + "\n"
                ).encode("utf-8")
            else:
                content = b"".join(
                    (json.dumps(record, ensure_ascii=False) + "\n").encode("utf-8")
                    for record in transformed
                )
            prepared[run_id][name] = content
    return prepared


def validate_output_root(output_candidate: Path) -> Path:
    if output_candidate.is_symlink():
        raise ValueError(f"output root is a symlink: {output_candidate}")
    output_root = output_candidate.resolve(strict=False)
    if output_root.exists() and not output_root.is_dir():
        raise ValueError(f"output root is not a directory: {output_root}")
    if output_root.exists():
        unexpected = {
            child.name for child in output_root.iterdir()
        } - set(APPROVED_RUN_IDS)
        if unexpected:
            raise ValueError(
                "unexpected existing output runs: "
                + ", ".join(sorted(unexpected))
            )
        for child in output_root.rglob("*"):
            if child.is_symlink():
                raise ValueError(f"unexpected output symlink: {child}")
    for run_id in APPROVED_RUN_IDS:
        destination = (output_root / run_id).resolve(strict=False)
        if not is_contained(destination, output_root):
            raise ValueError(f"output escapes resolved output root: {destination}")
    return output_root


def preflight_destinations(output_root: Path) -> dict[str, Path]:
    destinations: dict[str, Path] = {}
    for run_id in APPROVED_RUN_IDS:
        destination_run = output_root / run_id
        if destination_run.is_symlink():
            raise ValueError(f"output run is a symlink: {destination_run}")
        resolved_run = destination_run.resolve(strict=False)
        if not is_contained(resolved_run, output_root):
            raise ValueError(f"output run escapes resolved output root: {resolved_run}")
        if destination_run.exists():
            if not destination_run.is_dir():
                raise ValueError(f"output run path is not a directory: {destination_run}")
            unexpected = {
                path.name for path in destination_run.iterdir()
            } - set(ALLOWED_FILES)
            if unexpected:
                raise ValueError(
                    f"unexpected existing output for {run_id}: "
                    + ", ".join(sorted(unexpected))
                )
        for name in ALLOWED_FILES:
            destination = destination_run / name
            if destination.is_symlink():
                raise ValueError(f"output evidence is a symlink: {destination}")
            resolved_destination = destination.resolve(strict=False)
            if not is_contained(resolved_destination, resolved_run):
                raise ValueError(
                    f"output evidence escapes run directory: {resolved_destination}"
                )
            if destination.exists() and not destination.is_file():
                raise ValueError(f"output evidence is not a file: {destination}")
        destinations[run_id] = destination_run
    return destinations


def curate(logs_candidate: Path, output_candidate: Path) -> None:
    if logs_candidate.is_symlink():
        raise ValueError(f"logs root is a symlink: {logs_candidate}")
    logs_root = logs_candidate.resolve(strict=True)
    if not logs_root.is_dir():
        raise ValueError(f"logs root is not a directory: {logs_root}")
    if logs_root.name != "stage7_live" or logs_root.parent.name != "logs":
        raise ValueError(f"logs root must end with logs/stage7_live: {logs_root}")
    project_root = logs_root.parent.parent
    output_root = validate_output_root(output_candidate)

    parsed_runs = {
        run_id: validate_source_run(logs_root, run_id) for run_id in APPROVED_RUN_IDS
    }
    prepared = prepare_output(logs_root, project_root, parsed_runs)
    destinations = preflight_destinations(output_root)

    output_root.mkdir(parents=True, exist_ok=True)
    for run_id in APPROVED_RUN_IDS:
        destination_run = destinations[run_id]
        destination_run.mkdir(exist_ok=True)
        for name in ALLOWED_FILES:
            (destination_run / name).write_bytes(prepared[run_id][name])


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--logs-root", required=True, type=Path)
    parser.add_argument("--output-root", required=True, type=Path)
    args = parser.parse_args()
    try:
        curate(args.logs_root, args.output_root)
    except (OSError, ValueError, json.JSONDecodeError) as exc:
        print(f"[FAIL] PBL-1 evidence curation: {exc}", file=sys.stderr)
        return 2
    print(f"[PASS] curated {len(APPROVED_RUN_IDS)} approved PBL-1 runs")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
