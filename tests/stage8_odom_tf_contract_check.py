#!/usr/bin/env python3
"""The odometry contract checker must mirror MAVROS 1.20.1 odom plugin lookups."""

from __future__ import annotations

import argparse
import importlib.util
import json
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


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--module", required=True, type=Path)
    parser.add_argument("--config", required=True, type=Path)
    args = parser.parse_args()

    contract = load_module("odom_tf_contract_check", args.module)

    frames = contract.expected_tf_frames("uav1")
    for frame in (
        "uav1_map",
        "uav1_map_ned",
        "uav1_odom",
        "uav1_odom_ned",
        "uav1_camera_init",
        "uav1_body",
        "uav1_base_link",
        "uav1_base_link_frd",
        "uav1_lidar",
    ):
        assert frame in frames, f"missing expected TF frame {frame}"

    lookups = contract.mavros_lookup_pairs("uav1")
    expected_pairs = {
        ("uav1_map", "uav1_map_ned"),
        ("uav1_base_link", "uav1_base_link_frd"),
        ("uav1_odom_ned", "uav1_camera_init"),
        ("uav1_base_link_frd", "uav1_body"),
    }
    assert set(lookups) == expected_pairs, "lookup pairs must mirror the odom plugin"

    sample_log = "\n".join(
        '[ERROR] [1785665951.755377000]: ODOM: Ex: "uav1_map" passed to lookupTransform argument target_frame does not exist.'
        for _ in range(42)
    )
    parsed = contract.scan_mavros_log_errors(sample_log, "uav1")
    assert parsed["count"] == 42
    assert len(parsed["samples"]) > 0
    assert "uav1_map" in parsed["samples"][0]

    with tempfile.TemporaryDirectory() as temp_dir:
        report_path = Path(temp_dir) / "report.json"
        exit_code = contract.main(
            [
                "--config",
                str(args.config),
                "--backend",
                "dry-run",
                "--report",
                str(report_path),
            ]
        )
        assert exit_code == 0
        report = json.loads(report_path.read_text(encoding="utf-8"))
        assert report["ready"] is True
        assert {uav["uav_id"] for uav in report["uavs"]} == {"uav1", "uav2"}
        for uav in report["uavs"]:
            assert len(uav["lookups"]) == 4
            assert uav["lookups"][0]["target"] == f"{uav['uav_id']}_map"
            assert uav["lookups"][0]["source"] == f"{uav['uav_id']}_map_ned"

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
