#!/usr/bin/env python3
"""Run-scoped, read-only RflySim world-state retention probe for Competition Course V2."""

from __future__ import annotations

import argparse
import io
import json
import math
import os
import sys
import time
from contextlib import redirect_stdout
from pathlib import Path
from typing import Any, Dict, Iterable, List, Optional

from competition_course_geometry import load_spec
from competition_course_ue_loader import validated_runtime_entities
from narrow_course_geometry import Vec3, enu_to_ned, yaw_enu_to_ned


POSITION_TOLERANCE_M = 0.03
DIMENSION_TOLERANCE_M = 0.03
YAW_TOLERANCE_RAD = 0.05
PER_ENTITY_TIMEOUT_S = 1.5
DYNAMIC_MIN_Y_RANGE_M = 0.15
DYNAMIC_MIN_Z_RANGE_M = 0.02


def _wrap_angle(value: float) -> float:
    while value > math.pi:
        value -= 2.0 * math.pi
    while value < -math.pi:
        value += 2.0 * math.pi
    return value


def verify_receipt_scope(receipt_path: Path, spec_sha256: str, stack_id: str, simulation_instance_id: str) -> Dict[str, Any]:
    """A probe may only trust a receipt owned by this exact stack and instance."""
    if not stack_id or not simulation_instance_id:
        raise ValueError("world-state probe requires stack_id and simulation_instance_id scope")
    receipt_path = Path(receipt_path)
    if not receipt_path.exists():
        raise ValueError("run-scoped load receipt is missing: {}".format(receipt_path))
    try:
        receipt = json.loads(receipt_path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise ValueError("cannot read run-scoped load receipt: {}".format(exc)) from exc
    if receipt.get("spec_sha256") != spec_sha256 or receipt.get("cleanup_policy") != "receipt_only":
        raise ValueError("run-scoped load receipt does not match this course")
    if receipt.get("stack_id") != stack_id or receipt.get("simulation_instance_id") != simulation_instance_id:
        raise ValueError("cross-instance load receipt must not be used as world-state evidence")
    return receipt


def normalize_observation(raw: Any) -> Dict[str, Any]:
    return {
        "position_ned_m": [float(value) for value in raw.PosUE],
        "attitude_vendor_rad": [float(value) for value in raw.angEuler],
        "asset_local_dimensions_m": [2.0 * float(value) for value in raw.BoxExtent],
    }


def entity_errors(item: Dict[str, Any], observation: Dict[str, Any]) -> List[Dict[str, Any]]:
    """Deterministic static-contract errors for one entity observation."""
    errors: List[Dict[str, Any]] = []
    wanted_ned = [float(value) for value in enu_to_ned(Vec3(*(float(value) for value in item["center"])))]
    position = observation["position_ned_m"]
    if max(abs(actual - target) for actual, target in zip(position, wanted_ned)) > POSITION_TOLERANCE_M:
        errors.append({"id": item["id"], "kind": "position", "expected_ned_m": wanted_ned, "actual_ned_m": position})
    if item.get("yaw_rad") is not None and item["category"] != "aruco":
        expected_yaw = float(yaw_enu_to_ned(float(item["yaw_rad"])))
        actual_yaw = float(observation["attitude_vendor_rad"][2])
        if abs(_wrap_angle(actual_yaw - expected_yaw)) > YAW_TOLERANCE_RAD:
            errors.append({"id": item["id"], "kind": "yaw", "expected_ned_rad": expected_yaw, "actual_ned_rad": actual_yaw})
    if item.get("size") is not None and item["category"] != "aruco":
        dimensions = observation["asset_local_dimensions_m"]
        expected_size = [float(value) for value in item["size"]]
        if max(abs(actual - target) for actual, target in zip(dimensions, expected_size)) > DIMENSION_TOLERANCE_M:
            errors.append({"id": item["id"], "kind": "dimension", "expected_m": expected_size, "actual_m": dimensions})
    return errors


def evaluate_dynamic(dynamic_item: Dict[str, Any], samples: Iterable[Dict[str, Any]]) -> Dict[str, Any]:
    """Prove the pendulum exists at the right Scale and keeps moving."""
    samples = list(samples)
    result = {
        "object_id": dynamic_item["id"],
        "sample_count": len(samples),
        "dimensions_m": None,
        "motion_range_enu_m": None,
        "motion_errors": [],
    }
    if not samples:
        result["motion_errors"].append({"id": dynamic_item["id"], "kind": "no_samples", "detail": "pendulum produced no SDK updates"})
        return result
    result["dimensions_m"] = samples[-1]["asset_local_dimensions_m"]
    expected_size = [float(value) for value in dynamic_item["size"]]
    if max(abs(actual - target) for actual, target in zip(result["dimensions_m"], expected_size)) > DIMENSION_TOLERANCE_M:
        result["motion_errors"].append({
            "id": dynamic_item["id"], "kind": "dimension",
            "expected_m": expected_size, "actual_m": result["dimensions_m"],
            "detail": "native-size regression: motion update must keep spec-derived Scale",
        })
    xs = [float(sample["position_enu_m"][0]) for sample in samples]
    ys = [float(sample["position_enu_m"][1]) for sample in samples]
    zs = [float(sample["position_enu_m"][2]) for sample in samples]
    y_range = max(ys) - min(ys)
    z_range = max(zs) - min(zs)
    result["motion_range_enu_m"] = {"x": max(xs) - min(xs), "y": y_range, "z": z_range}
    if y_range < DYNAMIC_MIN_Y_RANGE_M or z_range < DYNAMIC_MIN_Z_RANGE_M:
        result["motion_errors"].append({
            "id": dynamic_item["id"], "kind": "motion",
            "y_range_m": y_range, "z_range_m": z_range,
            "required_y_range_m": DYNAMIC_MIN_Y_RANGE_M, "required_z_range_m": DYNAMIC_MIN_Z_RANGE_M,
            "detail": "pendulum position did not change enough over the observation window",
        })
    return result


def build_probe_report(
    probe_id: str,
    stack_id: str,
    simulation_instance_id: str,
    spec_sha256: str,
    entities: Iterable[Dict[str, Any]],
    observations: Dict[str, Dict[str, Any]],
    missing_ids: Iterable[int],
    errors_by_id: Dict[int, List[Dict[str, Any]]],
    dynamic: Dict[str, Any],
) -> Dict[str, Any]:
    entities = list(entities)
    errors = [error for errors in errors_by_id.values() for error in errors]
    if dynamic:
        errors += list(dynamic.get("motion_errors", []))
    missing = sorted(missing_ids)
    passed = not missing and not errors
    report = {
        "metadata": {
            "probe": "competition_course_v2_world_state",
            "probe_id": probe_id,
            "stack_id": stack_id,
            "simulation_instance_id": simulation_instance_id,
            "spec_sha256": spec_sha256,
            "created_at": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
        },
        "result": "PASS" if passed else "FAIL",
        "requested": len(entities),
        "observed": len(observations),
        "missing_ids": missing,
        "errors": errors,
        "dynamic": dynamic,
        "observations": observations,
    }
    return report


def query_entity(api, object_id: int, window_id: int, timeout_s: float = PER_ENTITY_TIMEOUT_S):
    with redirect_stdout(io.StringIO()):
        api.reqCamCoptObj(1, int(object_id), window_id)
    deadline = time.monotonic() + timeout_s
    while time.monotonic() < deadline:
        candidate = api.getCamCoptObj(1, int(object_id))
        if candidate is not None and candidate != 0 and getattr(candidate, "hasUpdate", False):
            candidate.hasUpdate = False
            return candidate
        time.sleep(0.01)
    return None


def collect_dynamic_samples(api, dynamic_item: Dict[str, Any], window_id: int, duration_s: float) -> Dict[str, Any]:
    samples: List[Dict[str, Any]] = []
    deadline = time.monotonic() + max(float(duration_s), 0.5)
    while time.monotonic() < deadline:
        raw = query_entity(api, int(dynamic_item["id"]), window_id, timeout_s=0.3)
        if raw is not None:
            record = normalize_observation(raw)
            ned = record["position_ned_m"]
            record["position_enu_m"] = [ned[1], ned[0], -ned[2]]
            samples.append(record)
        time.sleep(0.02)
    return evaluate_dynamic(dynamic_item, samples)


def probe_world(
    api,
    spec: Dict[str, Any],
    generated_manifest: Dict[str, Any],
    receipt_path: Path,
    stack_id: str,
    simulation_instance_id: str,
    probe_id: str,
    output: Path,
    window_id: int = 0,
    wait_before: float = 3.0,
    dynamic_sample_seconds: float = 2.5,
) -> Dict[str, Any]:
    if wait_before > 0:
        time.sleep(float(wait_before))
    verify_receipt_scope(receipt_path, spec["spec_sha256"], stack_id, simulation_instance_id)
    entities = validated_runtime_entities(spec, generated_manifest)
    api.initUE4MsgRec()
    try:
        observations: Dict[str, Dict[str, Any]] = {}
        missing: List[int] = []
        errors_by_id: Dict[int, List[Dict[str, Any]]] = {}
        for item in entities:
            raw = query_entity(api, int(item["id"]), window_id)
            if raw is None:
                missing.append(int(item["id"]))
                continue
            record = normalize_observation(raw)
            record["name"] = item["name"]
            record["category"] = item["category"]
            observations[str(item["id"])] = record
            errors = entity_errors(item, record)
            if errors:
                errors_by_id[int(item["id"])] = errors
        dynamic_item = next(item for item in entities if item["category"] == "dynamic_obstacle")
        dynamic: Dict[str, Any] = {"object_id": dynamic_item["id"], "sample_count": 0, "motion_errors": []}
        if int(dynamic_item["id"]) not in missing:
            dynamic = collect_dynamic_samples(api, dynamic_item, window_id, dynamic_sample_seconds)
    finally:
        end_receiver = getattr(api, "endUE4MsgRec", None)
        if callable(end_receiver):
            end_receiver()
    report = build_probe_report(
        probe_id=probe_id, stack_id=stack_id, simulation_instance_id=simulation_instance_id,
        spec_sha256=spec["spec_sha256"], entities=entities, observations=observations,
        missing_ids=missing, errors_by_id=errors_by_id, dynamic=dynamic,
    )
    output = Path(output)
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(report, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    return report


def _client(rflysim_root: Path):
    api_dir = Path(rflysim_root) / "RflySimAPIs/RflySimSDK/ue"
    if not api_dir.is_dir():
        raise RuntimeError("RflySim UE API directory missing: {}".format(api_dir))
    sys.path.insert(0, str(api_dir))
    import UE4CtrlAPI  # pylint: disable=import-error,import-outside-toplevel
    return UE4CtrlAPI.UE4CtrlAPI()


def main(argv: Optional[List[str]] = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--spec", type=Path, required=True)
    parser.add_argument("--generated", type=Path, required=True)
    parser.add_argument("--receipt", type=Path, required=True)
    parser.add_argument("--stack-id", required=True)
    parser.add_argument("--simulation-instance-id", required=True)
    parser.add_argument("--probe-id", required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--window-id", type=int, default=0)
    parser.add_argument("--wait-before", type=float, default=3.0)
    parser.add_argument("--dynamic-sample-seconds", type=float, default=2.5)
    parser.add_argument("--rflysim-root", type=Path, default=Path(os.environ.get("RFLYSIM_ROOT", r"D:\PX4PSP")))
    parser.add_argument("--dry-run", action="store_true")
    args = parser.parse_args(argv)
    spec = load_spec(args.spec)
    generated_manifest = json.loads((args.generated / "entity_manifest.json").read_text(encoding="utf-8"))
    entities = validated_runtime_entities(spec, generated_manifest)
    if args.dry_run:
        print(json.dumps({
            "mode": "dry-run", "probe_id": args.probe_id, "stack_id": args.stack_id,
            "simulation_instance_id": args.simulation_instance_id, "spec_sha256": spec["spec_sha256"],
            "receipt": str(args.receipt), "output": str(args.output),
            "wait_before_sec": args.wait_before, "dynamic_sample_seconds": args.dynamic_sample_seconds,
            "requested_ids": [item["id"] for item in entities],
        }, indent=2, sort_keys=True))
        return 0
    report = probe_world(
        _client(args.rflysim_root), spec, generated_manifest, args.receipt, args.stack_id,
        args.simulation_instance_id, args.probe_id, args.output, window_id=args.window_id,
        wait_before=args.wait_before, dynamic_sample_seconds=args.dynamic_sample_seconds,
    )
    print(json.dumps({
        "result": report["result"], "probe_id": args.probe_id, "requested": report["requested"],
        "observed": report["observed"], "missing_ids": report["missing_ids"],
        "error_count": len(report["errors"]), "output": str(args.output),
    }, indent=2, sort_keys=True))
    return 0 if report["result"] == "PASS" else 1


if __name__ == "__main__":
    raise SystemExit(main())
