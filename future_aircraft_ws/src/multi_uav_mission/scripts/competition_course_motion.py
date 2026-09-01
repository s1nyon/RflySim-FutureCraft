#!/usr/bin/env python3
"""Deterministic Competition Course V2 pendulum pose controller."""

from __future__ import annotations

import argparse
import json
import os
import sys
import time
from pathlib import Path
from typing import Any, Dict, Iterable

from competition_course_geometry import build_entity_manifest, load_spec, pendulum_pose
from narrow_course_geometry import Vec3, enu_to_ned


def _send(api, dynamic: Dict[str, Any], scale: Iterable[float], elapsed: float, window_id: int) -> Dict[str, Any]:
    pose = pendulum_pose(dynamic, elapsed)
    ned = list(enu_to_ned(Vec3(*pose)))
    api.sendUE4PosScale(
        copterID=dynamic["id"],
        vehicleType=dynamic["vehicle_type"],
        MotorRPMSMean=0,
        PosE=ned,
        AngEuler=[0.0, 0.0, 0.0],
        Scale=[float(value) for value in scale],
        windowID=window_id,
    )
    return {"elapsed_sec": round(float(elapsed), 6), "position_enu": [round(value, 6) for value in pose], "position_ned": [round(value, 6) for value in ned]}


def run_samples(api, dynamic: Dict[str, Any], scale: Iterable[float], elapsed_values: Iterable[float], evidence_path: Path, window_id: int = -1) -> Dict[str, Any]:
    scale = [float(value) for value in scale]
    samples = [_send(api, dynamic, scale, float(value), window_id) for value in elapsed_values]
    result = {"object_id": dynamic["id"], "scale": scale, "configured_amplitude_deg": dynamic["amplitude_deg"], "configured_period_sec": dynamic["period_sec"], "samples": samples}
    Path(evidence_path).parent.mkdir(parents=True, exist_ok=True); Path(evidence_path).write_text(json.dumps(result, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    return result


def _client(rflysim_root: Path):
    api_dir = rflysim_root / "RflySimAPIs/RflySimSDK/ue"; sys.path.insert(0, str(api_dir)); import UE4CtrlAPI  # pylint: disable=import-error,import-outside-toplevel
    return UE4CtrlAPI.UE4CtrlAPI()


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__); parser.add_argument("--spec", type=Path, required=True); parser.add_argument("--evidence", type=Path, required=True)
    parser.add_argument("--window-id", type=int, default=-1); parser.add_argument("--duration", type=float, default=0.0); parser.add_argument("--stop-file", type=Path)
    parser.add_argument("--rflysim-root", type=Path, default=Path(os.environ.get("RFLYSIM_ROOT", r"D:\PX4PSP"))); parser.add_argument("--dry-run", action="store_true")
    args = parser.parse_args(); spec = load_spec(args.spec); dynamic = spec["dynamic_obstacle"]
    dynamic_entity = next(entity for entity in build_entity_manifest(spec) if entity["id"] == dynamic["id"])
    scale = dynamic_entity["scale"]
    if args.dry_run:
        print(json.dumps({"mode": "dry-run", "object_id": dynamic["id"], "update_hz": dynamic["update_hz"], "samples": [pendulum_pose(dynamic, value) for value in (0, dynamic["period_sec"] / 4, dynamic["period_sec"] / 2)]}, indent=2)); return 0
    api, started, interval, samples = _client(args.rflysim_root), time.monotonic(), 1.0 / float(dynamic["update_hz"]), []
    args.evidence.parent.mkdir(parents=True, exist_ok=True)
    while True:
        elapsed = time.monotonic() - started; samples.append(_send(api, dynamic, scale, elapsed, args.window_id))
        if len(samples) > 400: samples = samples[-400:]
        if len(samples) == 1 or len(samples) % 20 == 0:
            args.evidence.write_text(json.dumps({"object_id": dynamic["id"], "scale": scale, "configured_amplitude_deg": dynamic["amplitude_deg"], "configured_period_sec": dynamic["period_sec"], "samples": samples}, indent=2, sort_keys=True) + "\n", encoding="utf-8")
        if (args.duration > 0 and elapsed >= args.duration) or (args.stop_file and args.stop_file.exists()): break
        time.sleep(interval)
    result = {"object_id": dynamic["id"], "scale": scale, "configured_amplitude_deg": dynamic["amplitude_deg"], "configured_period_sec": dynamic["period_sec"], "samples": samples}
    args.evidence.write_text(json.dumps(result, indent=2, sort_keys=True) + "\n", encoding="utf-8"); return 0


if __name__ == "__main__":
    raise SystemExit(main())
