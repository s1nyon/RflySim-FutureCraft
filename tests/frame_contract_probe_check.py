#!/usr/bin/env python3
"""Offline synthetic checks for the dual-UAV frame contract probe."""

from __future__ import annotations

import argparse
import importlib.util
import json
import tempfile
from pathlib import Path


def load_module(module_path: Path):
    spec = importlib.util.spec_from_file_location("frame_contract_probe", module_path)
    if spec is None or spec.loader is None:
        raise RuntimeError(f"cannot load module from {module_path}")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def sample(frame_id, child_frame_id="N/A", stamp=100.0, arrival=100.1):
    return {
        "header_frame_id": frame_id,
        "child_frame_id": child_frame_id,
        "header_stamp": stamp,
        "arrival_time": arrival,
    }


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--module", required=True, type=Path)
    args = parser.parse_args()
    probe = load_module(args.module)

    # Test 1: generic message-label reuse is not a cross-UAV TF edge.
    topics = {
        "/uav1/slam/odometry_raw": probe.build_topic_report(
            "/uav1/slam/odometry_raw",
            advertised=True,
            message_type="nav_msgs/Odometry",
            samples=[sample("camera_init", "body")],
        ),
        "/uav2/slam/odometry_raw": probe.build_topic_report(
            "/uav2/slam/odometry_raw",
            advertised=True,
            message_type="nav_msgs/Odometry",
            samples=[sample("camera_init", "body")],
        ),
    }
    generic_usage = probe.build_generic_frame_usage(topics)
    assert generic_usage["camera_init"]["status"] == "GENERIC_FRAME_REUSE"
    assert {item["topic"] for item in generic_usage["camera_init"]["used_by"]} == {
        "/uav1/slam/odometry_raw",
        "/uav2/slam/odometry_raw",
    }
    no_cross_tf = probe.build_transform_report(
        "uav1_camera_init", "uav2_camera_init", observation=None, cross_uav=True
    )
    report = {
        "topics": topics,
        "transforms": {"uav1_camera_init -> uav2_camera_init": no_cross_tf},
        "generic_frame_usage": generic_usage,
        "cross_uav_checks": {"topic_edges": [], "tf_edges": []},
    }
    summary = probe.build_summary(report)
    assert summary["generic_frame_labels_detected"] == ["body", "camera_init"]
    assert summary["cross_uav_tf_edges"] == 0

    # Test 2: a UAV1 topic claiming a UAV2 frame is an ERROR.
    wrong_uav = probe.build_topic_report(
        "/uav1/slam/odometry_raw",
        advertised=True,
        message_type="nav_msgs/Odometry",
        samples=[sample("uav2_body", "body")],
    )
    assert any(
        finding["severity"] == "ERROR"
        and finding["category"] == "CROSS_UAV_FRAME_LABEL"
        for finding in wrong_uav["header_findings"]
    )
    transient = probe.build_topic_report(
        "/uav1/slam/odometry_raw",
        advertised=True,
        message_type="nav_msgs/Odometry",
        samples=[sample("uav2_body", "body", arrival=100.0), sample("camera_init", "body", arrival=100.1)],
    )
    transient_errors = [
        item for item in transient["header_findings"] if item["category"] == "CROSS_UAV_FRAME_LABEL"
    ]
    assert len(transient_errors) == 1
    assert transient_errors[0]["occurrence_count"] == 1
    assert transient_errors[0]["first_arrival_time"] == 100.0

    # Test 3: an unadvertised topic is represented, not raised.
    missing = probe.build_topic_report("/uav1/rflysim/lidar", advertised=False)
    assert missing["status"] == "NOT_ADVERTISED"
    assert missing["header_frame_id"] == "N/A"
    assert missing["sample_count"] == 0

    # Test 4: advertised with no samples is distinct from missing.
    silent = probe.build_topic_report(
        "/uav1/rflysim/imu",
        advertised=True,
        message_type="sensor_msgs/Imu",
        publishers=["/uav1/rflysim_sensor"],
        samples=[],
    )
    assert silent["status"] == "NO_MESSAGE"
    assert silent["message_type"] == "sensor_msgs/Imu"

    # Test 5: an absent cross-UAV transform is nonfatal NO_TRANSFORM evidence.
    assert no_cross_tf["status"] == "NO_TRANSFORM"
    assert no_cross_tf["severity"] == "INFO"
    assert no_cross_tf["translation"] is None

    # Publisher/subscriber topology is observed and cross wiring is classified.
    wired = probe.build_topic_report(
        "/uav1/slam/cloud_registered",
        advertised=True,
        message_type="sensor_msgs/PointCloud2",
        subscribers=["/uav1/ego_grid", "/uav2/unexpected_consumer"],
        samples=[sample("camera_init")],
    )
    topic_edges = probe.find_cross_uav_topic_edges(
        {"/uav1/slam/cloud_registered": wired}
    )
    assert topic_edges[0]["status"] == "CROSS_UAV_SUBSCRIBER"
    cross_publisher = probe.build_topic_report(
        "/uav1/slam/cloud_registered",
        advertised=True,
        publishers=["/uav2/unexpected_source"],
        samples=[sample("camera_init")],
    )
    publisher_edges = probe.find_cross_uav_topic_edges(
        {"/uav1/slam/cloud_registered": cross_publisher}
    )
    assert publisher_edges[0]["status"] == "CROSS_UAV_PUBLISHER"

    # Late advertisements must become subscriptions rather than false NO_MESSAGE evidence.
    assert probe.newly_advertised_topics({}, set(), set()) == []
    assert probe.newly_advertised_topics(
        {"/uav1/rflysim/imu": "sensor_msgs/Imu"}, set(), set()
    ) == ["/uav1/rflysim/imu"]

    # The observer node is explicitly filtered while start/end graph evidence is retained.
    graph = probe.merge_graph_observations(
        "/uav1/rflysim/imu",
        [
            {"label": "start", "timestamp": 1.0, "publishers": ["/sensor"], "subscribers": []},
            {
                "label": "end",
                "timestamp": 2.0,
                "publishers": ["/sensor"],
                "subscribers": ["/frame_contract_probe_123", "/consumer"],
            },
        ],
        observer_node="/frame_contract_probe_123",
    )
    assert graph["publishers"] == ["/sensor"]
    assert graph["subscribers"] == ["/consumer"]
    assert len(graph["graph_observations"]) == 2

    # Multiple parents, duplicate broadcasters, and a present cross-UAV edge stay distinct.
    topology = probe.build_tf_topology_checks(
        {
            "world -> camera": {
                "parent": "world",
                "child": "camera",
                "broadcasters": ["/uav1/static", "/uav2/static"],
            },
            "map -> camera": {
                "parent": "map",
                "child": "camera",
                "broadcasters": ["/map_alias"],
            },
            "uav1_body -> uav2_body": {
                "parent": "uav1_body",
                "child": "uav2_body",
                "broadcasters": ["/unexpected_tf"],
            },
        }
    )
    assert topology["multiple_parent_children"] == [
        {"child": "camera", "parents": ["map", "world"]}
    ]
    assert topology["duplicate_tf_broadcasters"][0]["child"] == "camera"
    assert topology["direct_cross_uav_edges"][0]["status"] == "CROSS_UAV_TRANSFORM_PRESENT"
    present_cross_tf = probe.build_transform_report(
        "uav1_body",
        "uav2_body",
        observation={"translation": {"x": 1, "y": 0, "z": 0}, "rotation": {}, "lookup_timestamp": 5.0},
        cross_uav=True,
    )
    assert present_cross_tf["status"] == "CROSS_UAV_TRANSFORM_PRESENT"

    # Aggregate timing remains compact while exposing raw first/last values.
    timed = probe.build_topic_report(
        "/uav1/rflysim/imu",
        advertised=True,
        message_type="sensor_msgs/Imu",
        samples=[sample("imu", stamp=10.0, arrival=10.1), sample("imu", stamp=10.1, arrival=10.2)],
        timestamp_warn_ms=500.0,
    )
    assert timed["sample_count"] == 2
    assert timed["observed_frequency_hz"] == 10.0
    assert timed["age_ms"]["mean"] == 100.0
    assert timed["interarrival_gap_ms"] == {
        "minimum": 100.0,
        "maximum": 100.0,
        "mean": 100.0,
    }
    assert timed["first_sample"]["header_stamp"] == 10.0
    assert timed["last_sample"]["arrival_time"] == 10.2

    # Test 6: both report formats are emitted and JSON round-trips.
    report["metadata"] = {"timestamp": "2026-08-24T00:00:00Z"}
    report["frames"] = {}
    report["summary"] = summary
    with tempfile.TemporaryDirectory(prefix="frame-contract-probe-") as directory:
        paths = probe.write_reports(report, Path(directory))
        parsed = json.loads(paths["json"].read_text(encoding="utf-8"))
        assert parsed == report
        markdown = paths["markdown"].read_text(encoding="utf-8")
        assert "# Dual-UAV TF / Frame Contract Probe" in markdown
        assert "Generic Frame Usage" in markdown

    print("frame contract probe offline checks: PASS")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
