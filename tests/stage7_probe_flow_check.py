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

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
