#!/usr/bin/env python3
"""Run-scoped RflySim loader: idempotent upsert for the selected course."""

from __future__ import annotations

import argparse
import contextlib
import datetime
import hashlib
import json
import math
import os
import shutil
import sys
import time
import uuid
from pathlib import Path
from typing import Any, Dict, Iterator, List, Optional

from competition_course_geometry import build_entity_manifest, load_spec
from narrow_course_geometry import Vec3, enu_to_ned, yaw_enu_to_ned


INSTALLED_ARUCO_SHA256 = "0a2983af793349abc5cccb1e30c4a491263b63b6413be703a4a3f810fe9c592a"


def _sha(path: Path) -> str:
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def _atomic_copy(source: Path, target: Path) -> None:
    temporary = target.with_name("{}.{}.tmp".format(target.name, uuid.uuid4().hex))
    try:
        shutil.copyfile(str(source), str(temporary))
        os.replace(str(temporary), str(target))
    finally:
        if temporary.exists():
            temporary.unlink()


@contextlib.contextmanager
def installed_asset_transaction(source: Path, installed: Path, expected_sha256: str) -> Iterator[Dict[str, str]]:
    """Temporarily replace one fixed RflySim asset and byte-exactly restore it."""
    source, installed = Path(source), Path(installed)
    if not source.is_file() or not installed.is_file():
        raise ValueError("asset transaction source and installed paths must be files")
    original = installed.read_bytes()
    original_sha = hashlib.sha256(original).hexdigest()
    if original_sha.lower() != expected_sha256.lower():
        raise ValueError("installed ArUco fingerprint mismatch: {}".format(original_sha))
    evidence = {"original_sha256": original_sha, "replacement_sha256": _sha(source), "restored_sha256": "PENDING"}
    try:
        _atomic_copy(source, installed)
        if _sha(installed) != evidence["replacement_sha256"]:
            raise RuntimeError("installed ArUco replacement checksum mismatch")
        yield evidence
    finally:
        restore = installed.with_name("{}.{}.tmp".format(installed.name, uuid.uuid4().hex))
        try:
            restore.write_bytes(original)
            os.replace(str(restore), str(installed))
        finally:
            if restore.exists():
                restore.unlink()
        evidence["restored_sha256"] = _sha(installed)
        if evidence["restored_sha256"] != original_sha:
            raise RuntimeError("installed ArUco restore checksum mismatch")


def _ned(position: List[float]) -> List[float]:
    return list(enu_to_ned(Vec3(*(float(value) for value in position))))


STATIC_PASS_SETTLE_MIN_SECONDS = 0.1


def _utc_now() -> str:
    return datetime.datetime.utcnow().replace(microsecond=0).isoformat() + "Z"


def _load_owned_receipt(receipt_path: Path, spec_sha256: str, stack_id: Optional[str], simulation_instance_id: Optional[str]) -> List[int]:
    if not stack_id or not simulation_instance_id:
        raise ValueError("live load/unload requires stack_id and simulation_instance_id scope")
    if not receipt_path.exists():
        return []
    try:
        receipt = json.loads(receipt_path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise ValueError("cannot read run-scoped load receipt: {}".format(exc)) from exc
    if receipt.get("spec_sha256") != spec_sha256 or receipt.get("cleanup_policy") != "receipt_only":
        raise ValueError("run-scoped load receipt ownership does not match this course")
    if receipt.get("stack_id") != stack_id or receipt.get("simulation_instance_id") != simulation_instance_id:
        raise ValueError("cross-instance load receipt must not drive destroy/create for this stack/instance")
    ids = receipt.get("created_ids")
    if not isinstance(ids, list) or not all(isinstance(value, int) for value in ids):
        raise ValueError("run-scoped load receipt has invalid created_ids")
    return ids


def validated_runtime_entities(spec: Dict[str, Any], generated_manifest: Dict[str, Any]) -> List[Dict[str, Any]]:
    """Return spec-derived entities only after full generated-artifact parity."""
    expected = {
        "map_id": spec["map_id"],
        "coordinate_frame": "ENU",
        "spec_sha256": spec["spec_sha256"],
        "owned_cleanup": "receipt_only",
        "entities": build_entity_manifest(spec),
    }
    if not _manifest_matches(generated_manifest, expected):
        raise ValueError("generated entity manifest does not match spec-derived payload")
    return expected["entities"]


def _manifest_matches(actual: Dict[str, Any], expected: Dict[str, Any]) -> bool:
    """Full payload parity with float tolerance for cross-interpreter ULP noise.

    Metadata (map_id, coordinate_frame, spec_sha256, owned_cleanup) is compared
    strictly. Entity payloads are compared field-by-field; numbers use a tiny
    relative tolerance so Windows Python 3.8 generated artifacts are accepted
    by the WSL Python 3.10 runtime parity check while any real payload change
    (center/scale/id/name/extra entity) still fails closed.
    """
    if actual.keys() != expected.keys():
        return False
    for key in ("map_id", "coordinate_frame", "spec_sha256", "owned_cleanup"):
        if actual.get(key) != expected.get(key):
            return False
    actual_entities = actual.get("entities")
    expected_entities = expected.get("entities")
    if not isinstance(actual_entities, list) or not isinstance(expected_entities, list):
        return False
    if len(actual_entities) != len(expected_entities):
        return False
    return all(
        _entity_matches(actual_entity, expected_entity)
        for actual_entity, expected_entity in zip(actual_entities, expected_entities)
    )


def _entity_matches(actual: Any, expected: Any) -> bool:
    if isinstance(expected, float):
        return isinstance(actual, (int, float)) and math.isclose(
            float(actual), expected, rel_tol=1e-9, abs_tol=1e-9
        )
    if isinstance(expected, list):
        return (
            isinstance(actual, list)
            and len(actual) == len(expected)
            and all(_entity_matches(left, right) for left, right in zip(actual, expected))
        )
    if isinstance(expected, dict):
        return (
            isinstance(actual, dict)
            and actual.keys() == expected.keys()
            and all(_entity_matches(actual[key], value) for key, value in expected.items())
        )
    return actual == expected


def rflysim_box_request(item: Dict[str, Any], window_id: int) -> Dict[str, Any]:
    """Build the exact SDK request at the ENU-metres to RflySim boundary."""
    center, scale = item["center"], item["scale"]
    return {
        "copterID": item["id"],
        "vehicleType": item["vehicle_type"],
        "MotorRPMSMean": 0,
        "PosE": _ned(center),
        "AngEuler": [0.0, 0.0, yaw_enu_to_ned(float(item.get("yaw_rad", 0.0)))],
        "Scale": [float(value) for value in scale],
        "windowID": window_id,
    }


def _create_box(api, item: Dict[str, Any], window_id: int) -> None:
    api.sendUE4PosScale(**rflysim_box_request(item, window_id))


def _create_marker(api, marker: Dict[str, Any], source: Path, asset_path: Optional[Path], window_id: int, sleep, expected_asset_sha256: str) -> Dict[str, Any]:
    evidence: Dict[str, Any] = {"marker_id": marker["marker_id"], "source_sha256": _sha(source), "asset_transaction": "SKIPPED_OFFLINE"}
    transaction = installed_asset_transaction(source, asset_path, expected_asset_sha256) if asset_path is not None else contextlib.nullcontext({})
    with transaction as asset_evidence:
        api.sendUE4PosNew(copterID=marker["id"], vehicleType=marker["vehicle_type"], PosE=_ned(marker["center"]), AngEuler=[0.0, 90.0, yaw_enu_to_ned(0.0)], windowID=window_id)
        sleep(0.5)
        api.sendUE4ExtAct(copterID=marker["id"], ActExt=[marker["physical_size_m"], marker["white_border_size_m"]] + [0.0] * 14, windowID=window_id)
    if asset_path is not None:
        evidence["asset_transaction"] = dict(asset_evidence)
    return evidence


def load_scene(api, spec: Dict[str, Any], generated_manifest: Dict[str, Any], receipt_path: Path, marker_dir: Path, window_id: int, sleep=time.sleep, asset_path: Optional[Path] = None, expected_asset_sha256: str = INSTALLED_ARUCO_SHA256, stack_id: Optional[str] = None, simulation_instance_id: Optional[str] = None, static_passes: int = 2, static_settle_seconds: float = 0.3) -> Dict[str, Any]:
    if not stack_id or not simulation_instance_id:
        raise ValueError("live load requires stack_id and simulation_instance_id scope")
    if not isinstance(static_passes, int) or not 1 <= static_passes <= 3:
        raise ValueError("static_passes must be an integer in [1, 3]")
    if not STATIC_PASS_SETTLE_MIN_SECONDS <= static_settle_seconds <= 1.0:
        raise ValueError("static_settle_seconds must be in [0.1, 1.0]")
    entities = validated_runtime_entities(spec, generated_manifest)
    static_entities = [item for item in entities if item["category"] != "aruco"]
    marker_items = [item for item in entities if item["category"] == "aruco"]
    created, marker_evidence = [], []
    markers_by_name = {item["name"]: item for item in spec["landing"]["markers"]}
    try:
        for pass_index in range(static_passes):
            for item in static_entities:
                _create_box(api, item, window_id)
            created = [item["id"] for item in static_entities]
            if pass_index < static_passes - 1:
                sleep(static_settle_seconds)
        for item in marker_items:
            marker = dict(item); marker.update(markers_by_name[item["name"]])
            marker_evidence.append(_create_marker(api, marker, Path(marker_dir) / "marker_{}.png".format(marker["marker_id"]), asset_path, window_id, sleep, expected_asset_sha256))
            created.append(item["id"])
        api.sendUE4Cmd("RflyChangeViewKeyCmd P", window_id)
    except Exception:
        # Upsert is non-destructive: a failure must never destroy the selected
        # course's entities (they may predate this load on a running instance).
        failure = {
            "map_id": spec["map_id"], "spec_sha256": spec["spec_sha256"], "cleanup_policy": "receipt_only",
            "stack_id": stack_id, "simulation_instance_id": simulation_instance_id,
            "rollback_policy": "no_destroy_upsert", "rolled_back_ids": [],
            "load_result": "ROLLED_BACK", "created_at": _utc_now(),
        }
        Path(receipt_path).parent.mkdir(parents=True, exist_ok=True)
        Path(receipt_path).with_name("load_failure_receipt.json").write_text(json.dumps(failure, indent=2, sort_keys=True) + "\n", encoding="utf-8")
        raise
    receipt = {
        "map_id": spec["map_id"], "spec_sha256": spec["spec_sha256"], "cleanup_policy": "receipt_only",
        "stack_id": stack_id, "simulation_instance_id": simulation_instance_id, "created_at": _utc_now(),
        "delivery_policy": {
            "selected_course_destroy": False,
            "static_passes": int(static_passes),
            "static_settle_seconds": float(static_settle_seconds),
        },
        "created_ids": created, "window_id": window_id, "marker_evidence": marker_evidence,
    }
    Path(receipt_path).parent.mkdir(parents=True, exist_ok=True)
    Path(receipt_path).write_text(json.dumps(receipt, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    return receipt


def unload_scene(api, spec: Dict[str, Any], receipt_path: Path, window_id: int, motion_stop_file: Optional[Path] = None, sleep=time.sleep, stack_id: Optional[str] = None, simulation_instance_id: Optional[str] = None) -> Dict[str, Any]:
    """Stop course motion, then destroy only IDs proven by the matching run-scoped receipt."""
    receipt_path = Path(receipt_path)
    created_ids = _load_owned_receipt(receipt_path, spec["spec_sha256"], stack_id, simulation_instance_id)
    if not created_ids:
        raise ValueError("matching run-scoped load receipt is required for unload")
    if motion_stop_file is not None:
        Path(motion_stop_file).parent.mkdir(parents=True, exist_ok=True)
        Path(motion_stop_file).write_text("stop\n", encoding="ascii")
        sleep(1.0)
    for object_id in created_ids:
        api.sendUE4Destroy(object_id, window_id)
    result = {
        "map_id": spec["map_id"], "spec_sha256": spec["spec_sha256"], "cleanup_policy": "receipt_only",
        "stack_id": stack_id, "simulation_instance_id": simulation_instance_id, "created_at": _utc_now(),
        "destroyed_ids": created_ids, "motion_stop_requested": motion_stop_file is not None,
    }
    unload_receipt = receipt_path.with_name("unload_receipt.json")
    unload_receipt.write_text(json.dumps(result, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    receipt_path.unlink()
    return result


def _client(rflysim_root: Path):
    api_dir = rflysim_root / "RflySimAPIs/RflySimSDK/ue"
    if not api_dir.is_dir():
        raise RuntimeError("RflySim UE API directory missing: {}".format(api_dir))
    sys.path.insert(0, str(api_dir)); import UE4CtrlAPI  # pylint: disable=import-error,import-outside-toplevel
    return UE4CtrlAPI.UE4CtrlAPI()


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--spec", type=Path, required=True); parser.add_argument("--generated", type=Path, required=True)
    parser.add_argument("--receipt", type=Path, required=True); parser.add_argument("--window-id", type=int, default=-1)
    parser.add_argument("--asset-path", type=Path); parser.add_argument("--expected-asset-sha256", default=INSTALLED_ARUCO_SHA256)
    parser.add_argument("--rflysim-root", type=Path, default=Path(os.environ.get("RFLYSIM_ROOT", r"D:\PX4PSP"))); parser.add_argument("--dry-run", action="store_true")
    parser.add_argument("--unload", action="store_true"); parser.add_argument("--motion-stop-file", type=Path)
    parser.add_argument("--stack-id"); parser.add_argument("--simulation-instance-id")
    parser.add_argument("--static-passes", type=int, default=2); parser.add_argument("--static-settle-seconds", type=float, default=0.3)
    args = parser.parse_args(argv); spec = load_spec(args.spec)
    manifest = json.loads((args.generated / "entity_manifest.json").read_text(encoding="utf-8"))
    entities = validated_runtime_entities(spec, manifest)
    if args.dry_run:
        print(json.dumps({
            "mode": "dry-run", "operation": "unload" if args.unload else "load",
            "spec_sha256": spec["spec_sha256"], "receipt": str(args.receipt), "cleanup_policy": "receipt_only",
            "stack_id": args.stack_id, "simulation_instance_id": args.simulation_instance_id,
            "delivery_policy": {"selected_course_destroy": False, "static_passes": args.static_passes, "static_settle_seconds": args.static_settle_seconds},
            "create_ids": [] if args.unload else [item["id"] for item in entities],
            "would_replace_asset": str(args.asset_path) if args.asset_path and not args.unload else None,
        }, indent=2, sort_keys=True)); return 0
    if args.unload:
        print(json.dumps(unload_scene(_client(args.rflysim_root), spec, args.receipt, args.window_id, args.motion_stop_file, stack_id=args.stack_id, simulation_instance_id=args.simulation_instance_id), indent=2, sort_keys=True)); return 0
    receipt = load_scene(_client(args.rflysim_root), spec, manifest, args.receipt, args.generated / "aruco", args.window_id, asset_path=args.asset_path, expected_asset_sha256=args.expected_asset_sha256, stack_id=args.stack_id, simulation_instance_id=args.simulation_instance_id, static_passes=args.static_passes, static_settle_seconds=args.static_settle_seconds)
    print(json.dumps(receipt, indent=2, sort_keys=True)); return 0


if __name__ == "__main__":
    raise SystemExit(main())
