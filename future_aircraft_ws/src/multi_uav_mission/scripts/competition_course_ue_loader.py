#!/usr/bin/env python3
"""Receipt-owned RflySim loader with reversible ArUco asset transactions."""

from __future__ import annotations

import argparse
import contextlib
import hashlib
import json
import os
import shutil
import sys
import time
import uuid
from pathlib import Path
from typing import Any, Dict, Iterator, List, Optional

from competition_course_geometry import load_spec
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


def _load_prior_ids(receipt_path: Path, spec_sha256: str) -> List[int]:
    if not receipt_path.exists():
        return []
    try:
        receipt = json.loads(receipt_path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise ValueError("cannot read prior load receipt: {}".format(exc)) from exc
    if receipt.get("spec_sha256") != spec_sha256 or receipt.get("cleanup_policy") != "receipt_only":
        raise ValueError("prior load receipt ownership does not match this course")
    ids = receipt.get("created_ids")
    if not isinstance(ids, list) or not all(isinstance(value, int) for value in ids):
        raise ValueError("prior load receipt has invalid created_ids")
    return ids


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
    if asset_path is not None:
        evidence["asset_transaction"] = dict(asset_evidence)
    return evidence


def load_scene(api, spec: Dict[str, Any], generated_manifest: Dict[str, Any], receipt_path: Path, marker_dir: Path, window_id: int, sleep=time.sleep, asset_path: Optional[Path] = None, expected_asset_sha256: str = INSTALLED_ARUCO_SHA256) -> Dict[str, Any]:
    if generated_manifest.get("spec_sha256") != spec["spec_sha256"]:
        raise ValueError("entity manifest checksum does not match spec")
    prior_ids = _load_prior_ids(Path(receipt_path), spec["spec_sha256"])
    for object_id in prior_ids:
        api.sendUE4Destroy(object_id, window_id)
    entities = generated_manifest.get("entities")
    if not isinstance(entities, list):
        raise ValueError("entity manifest entities must be a list")
    created, marker_evidence = [], []
    markers_by_name = {item["name"]: item for item in spec["landing"]["markers"]}
    try:
        for item in entities:
            if item["category"] == "aruco":
                marker = dict(item); marker.update(markers_by_name[item["name"]])
                marker_evidence.append(_create_marker(api, marker, Path(marker_dir) / "marker_{}.png".format(marker["marker_id"]), asset_path, window_id, sleep, expected_asset_sha256))
            else:
                _create_box(api, item, window_id)
            created.append(item["id"])
        api.sendUE4Cmd("RflyChangeViewKeyCmd P", window_id)
    except Exception:
        for object_id in created:
            api.sendUE4Destroy(object_id, window_id)
        failure = {"map_id": spec["map_id"], "spec_sha256": spec["spec_sha256"], "cleanup_policy": "receipt_only", "rolled_back_ids": created, "load_result": "ROLLED_BACK"}
        Path(receipt_path).parent.mkdir(parents=True, exist_ok=True)
        Path(receipt_path).with_name("load_failure_receipt.json").write_text(json.dumps(failure, indent=2, sort_keys=True) + "\n", encoding="utf-8")
        raise
    receipt = {"map_id": spec["map_id"], "spec_sha256": spec["spec_sha256"], "cleanup_policy": "receipt_only", "created_ids": created, "window_id": window_id, "marker_evidence": marker_evidence}
    Path(receipt_path).parent.mkdir(parents=True, exist_ok=True)
    Path(receipt_path).write_text(json.dumps(receipt, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    return receipt


def unload_scene(api, spec: Dict[str, Any], receipt_path: Path, window_id: int, motion_stop_file: Optional[Path] = None, sleep=time.sleep) -> Dict[str, Any]:
    """Stop course motion, then destroy only IDs proven by the matching receipt."""
    receipt_path = Path(receipt_path)
    created_ids = _load_prior_ids(receipt_path, spec["spec_sha256"])
    if not created_ids:
        raise ValueError("matching load receipt is required for unload")
    if motion_stop_file is not None:
        Path(motion_stop_file).parent.mkdir(parents=True, exist_ok=True)
        Path(motion_stop_file).write_text("stop\n", encoding="ascii")
        sleep(1.0)
    for object_id in created_ids:
        api.sendUE4Destroy(object_id, window_id)
    result = {"map_id": spec["map_id"], "spec_sha256": spec["spec_sha256"], "cleanup_policy": "receipt_only", "destroyed_ids": created_ids, "motion_stop_requested": motion_stop_file is not None}
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


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--spec", type=Path, required=True); parser.add_argument("--generated", type=Path, required=True)
    parser.add_argument("--receipt", type=Path, required=True); parser.add_argument("--window-id", type=int, default=-1)
    parser.add_argument("--asset-path", type=Path); parser.add_argument("--expected-asset-sha256", default=INSTALLED_ARUCO_SHA256)
    parser.add_argument("--rflysim-root", type=Path, default=Path(os.environ.get("RFLYSIM_ROOT", r"D:\PX4PSP"))); parser.add_argument("--dry-run", action="store_true")
    parser.add_argument("--unload", action="store_true"); parser.add_argument("--motion-stop-file", type=Path)
    args = parser.parse_args(); spec = load_spec(args.spec)
    manifest = json.loads((args.generated / "entity_manifest.json").read_text(encoding="utf-8"))
    if args.dry_run:
        print(json.dumps({"mode": "dry-run", "operation": "unload" if args.unload else "load", "spec_sha256": spec["spec_sha256"], "receipt": str(args.receipt), "cleanup_policy": "receipt_only", "create_ids": [] if args.unload else [item["id"] for item in manifest["entities"]], "would_replace_asset": str(args.asset_path) if args.asset_path and not args.unload else None}, indent=2, sort_keys=True)); return 0
    if args.unload:
        print(json.dumps(unload_scene(_client(args.rflysim_root), spec, args.receipt, args.window_id, args.motion_stop_file), indent=2, sort_keys=True)); return 0
    receipt = load_scene(_client(args.rflysim_root), spec, manifest, args.receipt, args.generated / "aruco", args.window_id, asset_path=args.asset_path, expected_asset_sha256=args.expected_asset_sha256)
    print(json.dumps(receipt, indent=2, sort_keys=True)); return 0


if __name__ == "__main__":
    raise SystemExit(main())
