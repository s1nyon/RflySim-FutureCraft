#!/usr/bin/env python3
"""Contract checks for the Stage 2.1 single-UAV MAVLink return-path verifier."""

import argparse
import importlib.util
import json
from pathlib import Path


def load_module(script_path):
    spec = importlib.util.spec_from_file_location("mavlink_return_path_check", script_path)
    if spec is None or spec.loader is None:
        raise RuntimeError("cannot load verifier script: {}".format(script_path))
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--script", type=Path, required=True)
    args = parser.parse_args()

    repo_root = Path(__file__).resolve().parents[1]
    fixture_dir = repo_root / "tests" / "fixtures" / "stage2_1"
    module = load_module(args.script)

    assert module.load_config(repo_root / "config" / "stage2_1_mavlink_link.json") == {
        "stage": "2.1",
        "uav_id": "uav1",
        "namespace": "/uav1",
        "fcu_url": "udp://:16540@127.0.0.1:17540",
        "px4_instance": 1,
        "px4_out_log": "/mnt/d/PX4PSP/Firmware/build/px4_sitl_default/instance_1/out.log",
        "timeout_s": 10,
        "state_topic": "/uav1/mavros/state",
        "odom_topic": "/uav1/mavros/local_position/odom",
        "set_mode_service": "/uav1/mavros/set_mode",
        "arming_service": "/uav1/mavros/cmd/arming",
    }

    parsed = module.parse_px4_mavlink_status(
        (fixture_dir / "px4_status_ready.log").read_text(encoding="utf-8")
    )
    assert parsed == {
        "started": True,
        "mavlink_local_port": 17540,
        "mavlink_remote_port": 16540,
        "partner_ip": "127.0.0.1",
        "received_mavros_traffic": True,
    }

    blocked_parsed = module.parse_px4_mavlink_status(
        (fixture_dir / "px4_status_return_blocked.log").read_text(encoding="utf-8")
    )
    assert blocked_parsed == parsed

    expected_report = json.loads(
        (fixture_dir / "expected_dry_run_report.json").read_text(encoding="utf-8")
    )
    assert module.classify_report(
        expected_report["px4"], expected_report["mavros"]
    ) == expected_report["classification"]
    assert module.classify_report(
        {"started": False, "received_mavros_traffic": False},
        {"state_topic_present": True, "connected": True, "odom_received": True,
         "set_mode_service": True, "arming_service": True},
    ) == "px4_not_started"
    assert module.classify_report(
        {"started": True, "received_mavros_traffic": True},
        {"state_topic_present": False, "connected": False, "odom_received": False,
         "set_mode_service": False, "arming_service": False},
    ) == "mavros_not_started"
    assert module.classify_report(
        {"received_mavros_traffic": False},
        {"state_topic_present": True, "connected": False, "odom_received": False,
         "set_mode_service": True, "arming_service": True},
    ) == "mavros_to_px4_path_blocked"
    assert module.classify_report(
        {"received_mavros_traffic": True},
        {"state_topic_present": True, "connected": False, "odom_received": False,
         "set_mode_service": True, "arming_service": True},
    ) == "px4_to_mavros_return_path_blocked"
    assert module.classify_report(
        {"started": True, "received_mavros_traffic": True},
        {"state_topic_present": True, "connected": True, "odom_received": False,
         "set_mode_service": True, "arming_service": True},
    ) == "inconclusive"

if __name__ == "__main__":
    main()
