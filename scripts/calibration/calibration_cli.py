#!/usr/bin/env python3
"""DryRun-first command entry for official asset metadata calibration."""

from __future__ import annotations

import argparse
import json
import os
import sys
import time
from pathlib import Path

from asset_catalog import load_catalog
from calibration_artifacts import generate_artifacts
from object_metadata import (
    MetadataCaptureError,
    MetadataValidationError,
    analyze_samples,
    build_metadata_profile,
    close_metadata_receiver,
    initialize_metadata_receiver,
    record_candidate,
)
from ue_asset_loader import build_commands, place_assets, remove_assets


def _create_client(rflysim_root: Path):
    api_dir = rflysim_root / "RflySimAPIs" / "RflySimSDK" / "ue"
    if not api_dir.is_dir():
        raise RuntimeError("RflySim UE API directory does not exist: {}".format(api_dir))
    sys.path.insert(0, str(api_dir))
    import UE4CtrlAPI  # pylint: disable=import-error,import-outside-toplevel

    return UE4CtrlAPI.UE4CtrlAPI()


def _dry_receipt(action, catalog):
    receipt = {
        "acted_on_ids": [item.object_id for item in build_commands(catalog)],
        "action": action,
        "arming_request": False,
        "catalog_sha256": catalog.sha256,
        "map_change": False,
        "mode": "dry-run",
    }
    if action == "load":
        receipt["placements"] = [
            {
                "class_id": command.class_id,
                "object_id": command.object_id,
                "position_enu_m": list(candidate.position_enu),
                "position_ned_m": list(command.position_ned),
                "scale": list(command.scale),
                "yaw_enu_rad": candidate.yaw_enu_rad,
                "yaw_ned_rad": command.yaw_ned_rad,
            }
            for candidate, command in zip(catalog.assets, build_commands(catalog))
        ]
    return receipt


def _write_json(path: Path, payload):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True) + "\n", encoding="utf-8")


def _record(client, catalog, output, samples, timeout_s, run_id, stack_instance_id):
    output.mkdir(parents=True, exist_ok=True)
    initialize_metadata_receiver(client)
    states = []
    profile_paths = []
    try:
        for candidate in catalog.assets:
            try:
                captured = record_candidate(client, candidate, samples, timeout_s)
                analysis = analyze_samples(candidate, captured, placement_plane_z=catalog.placement_z)
            except (MetadataCaptureError, MetadataValidationError) as exc:
                analysis = analyze_samples(
                    candidate, getattr(exc, "samples", []), placement_plane_z=catalog.placement_z
                )
                reason = "CAPTURE_TIMEOUT" if isinstance(exc, MetadataCaptureError) else "INVALID_METADATA"
                analysis["rejection_reasons"].insert(0, reason)
                analysis["capture_error"] = str(exc)
            profile = build_metadata_profile(
                candidate,
                analysis,
                {
                    "catalog_sha256": catalog.sha256,
                    "captured_at_unix_s": time.time(),
                    "run_id": run_id,
                    "stack_instance_id": stack_instance_id,
                },
            )
            path = output / "{}.json".format(candidate.key)
            _write_json(path, profile)
            profile_paths.append(path.name)
            states.append(profile["evidence_state"])
    finally:
        close_metadata_receiver(client)
    manifest = {
        "arming_request": False,
        "catalog_sha256": catalog.sha256,
        "map_change": False,
        "profiles": profile_paths,
        "run_id": run_id,
        "stack_instance_id": stack_instance_id,
        "states": states,
    }
    _write_json(output / "metadata_run_manifest.json", manifest)
    return manifest, all(state == "METADATA_MEASURED" for state in states)


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    subparsers = parser.add_subparsers(dest="command", required=True)
    generate = subparsers.add_parser("generate")
    generate.add_argument("--catalog", type=Path, required=True)
    generate.add_argument("--output", type=Path, required=True)
    for name in ("load", "remove"):
        action = subparsers.add_parser(name)
        action.add_argument("--catalog", type=Path, required=True)
        action.add_argument("--execute", action="store_true")
        action.add_argument("--window-id", type=int, default=-1)
        action.add_argument("--rflysim-root", type=Path, default=Path(os.environ.get("RFLYSIM_ROOT", r"D:\PX4PSP")))
    record = subparsers.add_parser("record")
    record.add_argument("--catalog", type=Path, required=True)
    record.add_argument("--output", type=Path, required=True)
    record.add_argument("--execute", action="store_true")
    record.add_argument("--samples", type=int, default=5)
    record.add_argument("--timeout-s", type=float, default=10.0)
    record.add_argument("--run-id")
    record.add_argument("--stack-instance-id")
    record.add_argument("--rflysim-root", type=Path, default=Path(os.environ.get("RFLYSIM_ROOT", r"D:\PX4PSP")))
    args = parser.parse_args(argv)
    catalog = load_catalog(args.catalog)

    if args.command == "generate":
        print(json.dumps(generate_artifacts(args.catalog, args.output), indent=2, sort_keys=True))
        return 0
    if not args.execute:
        print(json.dumps(_dry_receipt(args.command, catalog), indent=2, sort_keys=True))
        return 0
    if args.command == "record":
        if not args.run_id:
            parser.error("record --execute requires --run-id")
        if not args.stack_instance_id:
            parser.error("record --execute requires --stack-instance-id")
    client = _create_client(args.rflysim_root)
    if args.command == "load":
        receipt = place_assets(client, catalog, args.window_id)
        print(json.dumps(receipt, indent=2, sort_keys=True))
        return 0
    if args.command == "remove":
        receipt = remove_assets(client, catalog, args.window_id)
        print(json.dumps(receipt, indent=2, sort_keys=True))
        return 0
    manifest, passed = _record(
        client, catalog, args.output, args.samples, args.timeout_s, args.run_id, args.stack_instance_id
    )
    print(json.dumps(manifest, indent=2, sort_keys=True))
    return 0 if passed else 1


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except Exception as exc:  # bounded CLI diagnostic
        print("asset calibration error: {}".format(exc), file=sys.stderr)
        raise SystemExit(1)
