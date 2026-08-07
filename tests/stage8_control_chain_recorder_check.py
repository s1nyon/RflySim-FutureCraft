#!/usr/bin/env python3
"""Stage 8 read-only control-chain recorder must stay read-only and forensic."""

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
    parser.add_argument("--recorder-module", required=True, type=Path)
    parser.add_argument("--config", required=True, type=Path)
    args = parser.parse_args()

    recorder = load_module("stage8_control_chain_recorder", args.recorder_module)
    config = json.loads(args.config.read_text(encoding="utf-8"))

    # z summaries must count out-of-geofence samples explicitly.
    assert recorder.summarize_z_samples([], 0.0, 2.0) == {
        "count": 0,
        "min_z": None,
        "max_z": None,
        "outside_count": 0,
        "outside_min_z": None,
        "outside_max_z": None,
    }
    assert recorder.summarize_z_samples([1.0, 1.5, 0.2], 0.0, 2.0) == {
        "count": 3,
        "min_z": 0.2,
        "max_z": 1.5,
        "outside_count": 0,
        "outside_min_z": None,
        "outside_max_z": None,
    }
    assert recorder.summarize_z_samples([1.0, 3.0, -0.5], 0.0, 2.0) == {
        "count": 3,
        "min_z": -0.5,
        "max_z": 3.0,
        "outside_count": 2,
        "outside_min_z": -0.5,
        "outside_max_z": 3.0,
    }

    # Setpoint z is only a commanded position when IGNORE_PZ is not masked.
    assert recorder.setpoint_z_commanded(0) is True
    assert recorder.setpoint_z_commanded(4) is False  # IGNORE_PZ
    assert recorder.setpoint_z_commanded(7) is False  # ignore px/py/pz
    assert recorder.setpoint_z_commanded(8) is True  # ignore vx only

    # Every event must carry wall, monotonic, and header time sources.
    event = recorder.control_event(
        "planner_command",
        "uav1",
        receive_wall_time=1000.0,
        receive_monotonic=5.0,
        header_stamp=4.0,
        position=[0.0, 0.0, 1.0],
        yaw=0.0,
    )
    assert event["kind"] == "planner_command"
    assert event["uav_id"] == "uav1"
    assert event["receive_wall_time"] == 1000.0
    assert event["receive_monotonic"] == 5.0
    assert event["header_stamp"] == 4.0
    assert event["position"] == [0.0, 0.0, 1.0]

    state_event = recorder.control_event(
        "state_change",
        "uav2",
        receive_wall_time=1001.0,
        receive_monotonic=6.0,
        mode="MANUAL",
        armed=False,
    )
    assert state_event["header_stamp"] is None

    # Mode changes compress into segments with first/last monotonic times.
    changes = recorder.summarize_mode_changes(
        [
            {"mode": "MANUAL", "armed": False, "receive_monotonic": 1.0},
            {"mode": "MANUAL", "armed": False, "receive_monotonic": 2.0},
            {"mode": "OFFBOARD", "armed": True, "receive_monotonic": 3.0},
            {"mode": "OFFBOARD", "armed": True, "receive_monotonic": 4.0},
        ]
    )
    assert len(changes) == 2
    assert changes[0] == {
        "mode": "MANUAL",
        "armed": False,
        "first_receive_monotonic": 1.0,
        "last_receive_monotonic": 2.0,
        "count": 2,
    }
    assert changes[1] == {
        "mode": "OFFBOARD",
        "armed": True,
        "first_receive_monotonic": 3.0,
        "last_receive_monotonic": 4.0,
        "count": 2,
    }

    with tempfile.TemporaryDirectory() as temp_dir:
        output = Path(temp_dir) / "stage8_control_chain.jsonl"
        exit_code = recorder.main(
            [
                "--config",
                str(args.config),
                "--backend",
                "dry-run",
                "--duration-s",
                "10",
                "--output",
                str(output),
                "--run-id",
                "stage8-dry-run",
            ]
        )
        assert exit_code == 0
        assert output.exists()
        assert output.read_text(encoding="utf-8") == ""
        summary_path = Path(temp_dir) / "stage8_control_chain_summary.json"
        assert summary_path.exists()
        summary = json.loads(summary_path.read_text(encoding="utf-8"))
        assert summary["backend"] == "dry-run"
        assert summary["run_id"] == "stage8-dry-run"
        assert summary["geofence_z"] == [-0.5, 2.0], (
            "recorder default geofence must match the course z floor"
        )
        assert set(summary["uavs"].keys()) == {"uav1", "uav2"}
        for uav_id, uav_summary in summary["uavs"].items():
            assert uav_summary["planner_command_count"] == 0
            assert uav_summary["setpoint_target_count"] == 0
            assert uav_summary["setpoint_z_commanded"]["count"] == 0
            assert uav_summary["setpoint_z_ignored_count"] == 0
            assert uav_summary["slam_raw_odometry_count"] == 0
            assert uav_summary["mavros_odom_out_count"] == 0
            assert uav_summary["mavros_odom_in_count"] == 0
            assert uav_summary["local_position_count"] == 0
            assert uav_summary["mode_changes"] == []

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
