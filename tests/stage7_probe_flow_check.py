#!/usr/bin/env python3
"""Topic probe must verify real goal subscribers and planner command flow."""

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
    parser.add_argument("--probe-module", required=True, type=Path)
    parser.add_argument("--config", required=True, type=Path)
    args = parser.parse_args()

    probe = load_module("stage7_topic_probe", args.probe_module)
    config = json.loads(args.config.read_text(encoding="utf-8"))

    # Pure subscriber-count parser against a synthetic ROS master state.
    system_state = (
        [("/uav1/planning/pos_cmd", [("node-a", "tcp")])],
        [
            ("/uav1/planning/goal", [("node-b", "tcp"), ("node-c", "udp")]),
            ("/other/topic", [("node-d", "tcp")]),
        ],
        [],
    )
    assert probe.parse_subscriber_count(system_state, "/uav1/planning/goal") == 2
    assert probe.parse_subscriber_count(system_state, "/uav1/planning/pos_cmd") == 0

    flow = probe.summarize_message_flow([0.2, 0.9, 1.7], now=3.0)
    assert flow == {"count": 3, "first_latency_s": 0.2, "last_age_s": 1.3}
    empty = probe.summarize_message_flow([], now=3.0)
    assert empty["count"] == 0
    assert empty["first_latency_s"] is None
    assert empty["last_age_s"] is None

    # D435i transport contract: the probe must count real publishers and
    # summarize mono16 depth image flow, not just mark topics as planned.
    publisher_state = (
        [
            ("/uav1/rflysim/sensor3/img_depth", [("relay-a", "tcp"), ("relay-b", "udp")]),
            ("/uav2/rflysim/sensor13/img_depth", [("relay-c", "tcp")]),
        ],
        [],
        [],
    )
    assert probe.parse_publisher_count(
        publisher_state, "/uav1/rflysim/sensor3/img_depth"
    ) == 2
    assert probe.parse_publisher_count(
        publisher_state, "/uav2/rflysim/sensor13/img_depth"
    ) == 1
    assert probe.parse_publisher_count(publisher_state, "/uav1/rflysim/lidar") == 0

    two_pixels = b"\x00\x00\x64\x00\xff\xff"
    assert probe.depth_image_stats(two_pixels) == {
        "zero_ratio": round(1 / 3, 4),
        "min_depth": 0,
        "max_depth": 65535,
    }
    assert probe.depth_image_stats(b"") == {
        "zero_ratio": 1.0,
        "min_depth": None,
        "max_depth": None,
    }
    assert probe.depth_image_stats(b"\x00\x00\x00\x00") == {
        "zero_ratio": 1.0,
        "min_depth": 0,
        "max_depth": 0,
    }

    depth_samples = [
        {
            "receive": 10.0,
            "header_stamp": 5.0,
            "data": b"\x00\x00\x64\x00",
            "encoding": "mono16",
            "width": 640,
            "height": 480,
        },
        {
            "receive": 10.1,
            "header_stamp": 5.1,
            "data": b"\xff\xff\x64\x00",
            "encoding": "mono16",
            "width": 640,
            "height": 480,
        },
    ]
    depth_summary = probe.summarize_depth_flow(
        depth_samples, now=10.2, duration_s=5.0
    )
    assert depth_summary["count"] == 2
    assert depth_summary["receive_rate_hz"] == round(2 / 5.0, 2)
    assert depth_summary["header_rate_hz"] == 10.0
    assert depth_summary["stamp_monotonic"] is True
    assert depth_summary["any_nonzero_sample"] is True
    assert depth_summary["encoding"] == "mono16"
    assert depth_summary["width"] == 640
    assert depth_summary["height"] == 480
    assert depth_summary["last_zero_ratio"] == 0.0
    assert depth_summary["last_min_depth"] == 100
    assert depth_summary["last_max_depth"] == 65535
    assert depth_summary["last_age_s"] == round(10.2 - 10.1, 3)

    non_monotonic = probe.summarize_depth_flow(
        [
            {
                "receive": 10.0,
                "header_stamp": 5.1,
                "data": b"\x64\x00\x00\x00",
            },
            {
                "receive": 10.1,
                "header_stamp": 5.0,
                "data": b"\x00\x00\x64\x00",
            },
        ],
        now=10.2,
        duration_s=5.0,
    )
    assert non_monotonic["stamp_monotonic"] is False
    assert non_monotonic["any_nonzero_sample"] is True

    empty_depth = probe.summarize_depth_flow([], now=10.0, duration_s=5.0)
    assert empty_depth["count"] == 0
    assert empty_depth["receive_rate_hz"] == 0.0
    assert empty_depth["header_rate_hz"] is None
    assert empty_depth["stamp_monotonic"] is True
    assert empty_depth["any_nonzero_sample"] is False
    assert empty_depth["encoding"] is None

    with tempfile.TemporaryDirectory() as temp_dir:
        report_path = Path(temp_dir) / "probe.json"
        exit_code = probe.main(
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
        kinds = {
            check["kind"]
            for check in report["layers"]["ego_swarm"]["checks"]
        }
        assert "topic_subscriber_count" in kinds, (
            "ego-swarm layer must verify real goal subscribers, not publisher creation"
        )
        assert "topic_message_flow" in kinds, (
            "ego-swarm layer must verify planner command message flow"
        )
        ego_checks = report["layers"]["ego_swarm"]["checks"]
        subscriber_targets = {
            check["target"]
            for check in ego_checks
            if check["kind"] == "topic_subscriber_count"
        }
        flow_targets = {
            check["target"]
            for check in ego_checks
            if check["kind"] == "topic_message_flow"
        }
        assert subscriber_targets == {"/uav1/planning/goal", "/uav2/planning/goal"}
        assert flow_targets == {"/uav1/planning/pos_cmd", "/uav2/planning/pos_cmd"}
        for check in ego_checks:
            if check["kind"] == "topic_subscriber_count":
                assert check["name"] == "planner_goal_subscribers"
                assert check["min_count"] >= 1
            if check["kind"] == "topic_message_flow":
                assert check["name"] == "planner_cmd_flow"
                assert check["duration_s"] > 0
                assert check["min_messages"] >= 1
            assert check["ready"] is True, "dry-run checks must be planned-ready"

        sensor_bridge_checks = report["layers"]["sensor_bridge"]["checks"]
        depth_publisher_checks = [
            check
            for check in sensor_bridge_checks
            if check["kind"] == "topic_publisher_count"
        ]
        assert {check["name"] for check in depth_publisher_checks} == {
            "depth_publisher_count"
        }
        assert {
            check["target"] for check in depth_publisher_checks
        } == {
            "/uav1/rflysim/sensor3/img_depth",
            "/uav2/rflysim/sensor13/img_depth",
        }
        assert all(
            check["min_count"] == 1 and check["max_count"] == 1
            for check in depth_publisher_checks
        )
        depth_flow_checks = [
            check
            for check in sensor_bridge_checks
            if check["kind"] == "depth_image_flow"
        ]
        assert {check["name"] for check in depth_flow_checks} == {"depth_flow"}
        assert all(
            check["expected_encoding"] == "mono16"
            and check["expected_width"] == 640
            and check["expected_height"] == 480
            and check["min_rate_hz"] == 20
            and check["max_rate_hz"] == 45
            for check in depth_flow_checks
        )
        assert all(check["ready"] is True for check in depth_flow_checks)

        # validate_config must reject a config missing the new vision fields.
        import copy

        broken_uav = copy.deepcopy(config)
        del broken_uav["uavs"][0]["sensor_depth_topic"]
        try:
            probe.validate_config(broken_uav)
            raise AssertionError(
                "validate_config must reject a UAV without sensor_depth_topic"
            )
        except ValueError:
            pass

        broken_bridge = copy.deepcopy(config)
        del broken_bridge["fast_lio"]["bridges"][0]["raw_depth_topic"]
        try:
            probe.validate_config(broken_bridge)
            raise AssertionError(
                "validate_config must reject a bridge without raw_depth_topic"
            )
        except ValueError:
            pass

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
