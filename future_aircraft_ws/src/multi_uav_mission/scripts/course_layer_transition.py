#!/usr/bin/env python3
"""Destroy only IDs declared by tracked project course specs during transitions."""

from __future__ import annotations

import argparse
import datetime
import hashlib
import json
import os
import sys
import uuid
from pathlib import Path
from typing import Any, Dict, Iterable, List, Mapping, Tuple

from competition_course_geometry import build_entity_manifest, load_spec as load_v2_spec
from narrow_course_geometry import load_course


COURSE_NAMES = ("predicted_narrow_course", "competition_course_v2")


def _atomic_json(path: Path, value: Dict[str, Any]) -> None:
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_name("{}.{}.tmp".format(path.name, uuid.uuid4().hex))
    try:
        temporary.write_text(json.dumps(value, indent=2, sort_keys=True) + "\n", encoding="utf-8")
        os.replace(str(temporary), str(path))
    finally:
        if temporary.exists():
            temporary.unlink()


def build_transition_plan(selected: str, declared_ids: Mapping[str, Iterable[int]]) -> Dict[str, Any]:
    if selected not in COURSE_NAMES:
        raise ValueError("unknown selected course: {}".format(selected))
    if set(declared_ids) != set(COURSE_NAMES):
        raise ValueError("declared course names must be exactly {}".format(", ".join(COURSE_NAMES)))
    normalized: Dict[str, List[int]] = {}
    owner_by_id: Dict[int, str] = {}
    for course in COURSE_NAMES:
        values = list(declared_ids[course])
        if not all(isinstance(value, int) and not isinstance(value, bool) for value in values):
            raise ValueError("declared entity IDs must be integers")
        if len(values) != len(set(values)):
            raise ValueError("duplicate declared entity ID within {}".format(course))
        normalized[course] = sorted(values)
        for object_id in values:
            if object_id in owner_by_id:
                raise ValueError("entity ID {} is declared by multiple courses".format(object_id))
            owner_by_id[object_id] = course
    return {
        "selected_course": selected,
        "declared_ids": normalized,
        "destroy_ids": sorted(owner_by_id),
        "cleanup_policy": "exact_declared_ids",
    }


def execute_transition(api, plan: Dict[str, Any], receipt_path: Path, window_id: int) -> Dict[str, Any]:
    sent: List[int] = []
    timestamp = datetime.datetime.utcnow().replace(microsecond=0).isoformat() + "Z"
    try:
        for object_id in plan["destroy_ids"]:
            api.sendUE4Destroy(object_id, window_id)
            sent.append(object_id)
    except Exception:
        failure = {
            "cleanup_policy": "exact_declared_ids",
            "command_status": "FAILED",
            "destroy_requested_ids": list(plan["destroy_ids"]),
            "destroy_commands_sent_ids": sent,
            "selected_course": plan["selected_course"],
            "source_hashes": dict(plan.get("source_hashes", {})),
            "timestamp_utc": timestamp,
            "window_id": window_id,
        }
        _atomic_json(Path(receipt_path).with_name("transition_failure_receipt.json"), failure)
        raise
    receipt = {
        "cleanup_policy": "exact_declared_ids",
        "command_status": "COMMANDS_SENT",
        "destroy_requested_ids": list(plan["destroy_ids"]),
        "selected_course": plan["selected_course"],
        "source_hashes": dict(plan.get("source_hashes", {})),
        "timestamp_utc": timestamp,
        "window_id": window_id,
    }
    _atomic_json(receipt_path, receipt)
    return receipt


def declared_course_sources(project_root: Path) -> Tuple[Dict[str, List[int]], Dict[str, str]]:
    project_root = Path(project_root).resolve()
    predicted_path = project_root / "config/maps/predicted_narrow_course_v1.json"
    v2_path = project_root / "config/maps/competition_course_v2.json"
    predicted = load_course(predicted_path)
    v2 = load_v2_spec(v2_path)
    declared = {
        "predicted_narrow_course": [item.copter_id for item in predicted.scene_objects],
        "competition_course_v2": [item["id"] for item in build_entity_manifest(v2)],
    }
    ranges = {
        "predicted_narrow_course": tuple(predicted.owned_id_range),
        "competition_course_v2": tuple(v2["object_id_range"]),
    }
    if not (ranges["predicted_narrow_course"][1] < ranges["competition_course_v2"][0] or
            ranges["competition_course_v2"][1] < ranges["predicted_narrow_course"][0]):
        raise ValueError("tracked project course ID ranges overlap")
    for course in COURSE_NAMES:
        low, high = ranges[course]
        if not declared[course] or any(not low <= object_id <= high for object_id in declared[course]):
            raise ValueError("{} declares an ID outside its reserved range".format(course))
    hashes = {
        "predicted_narrow_course": predicted.spec_sha256,
        "competition_course_v2": v2["spec_sha256"],
    }
    return declared, hashes


def _client(rflysim_root: Path):
    api_dir = Path(rflysim_root) / "RflySimAPIs/RflySimSDK/ue"
    if not api_dir.is_dir():
        raise RuntimeError("RflySim UE API directory missing: {}".format(api_dir))
    sys.path.insert(0, str(api_dir))
    import UE4CtrlAPI  # pylint: disable=import-error,import-outside-toplevel
    return UE4CtrlAPI.UE4CtrlAPI()


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--project-root", type=Path, required=True)
    parser.add_argument("--selected", choices=COURSE_NAMES, required=True)
    parser.add_argument("--receipt", type=Path, required=True)
    parser.add_argument("--window-id", type=int, default=-1)
    parser.add_argument("--rflysim-root", type=Path, default=Path(os.environ.get("RFLYSIM_ROOT", r"D:\PX4PSP")))
    parser.add_argument("--dry-run", action="store_true")
    args = parser.parse_args()
    declared, hashes = declared_course_sources(args.project_root)
    plan = build_transition_plan(args.selected, declared)
    plan["source_hashes"] = hashes
    if args.dry_run:
        output = dict(plan)
        output["mode"] = "dry-run"
    else:
        output = execute_transition(_client(args.rflysim_root), plan, args.receipt, args.window_id)
    print(json.dumps(output, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
