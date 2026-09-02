#!/usr/bin/env python3
"""Capture a bounded, read-only dual-UAV ROS topic and TF evidence report.

The probe only subscribes to existing topics and queries tf2.  It does not
publish messages, set parameters, alter transforms, or act as a health gate.
ROS imports are deliberately delayed so offline report tests and ``--help`` do
not require a ROS installation.
"""

from __future__ import annotations

import argparse
import json
import os
import socket
import subprocess
import sys
import threading
import time
from datetime import datetime, timezone
from pathlib import Path


TOPICS = tuple(
    f"/uav{uav}/{suffix}"
    for uav in (1, 2)
    for suffix in (
        "rflysim/lidar",
        "rflysim/imu",
        "slam/odometry_raw",
        "slam/cloud_registered",
        "slam/cloud_registered_body",
        "mavros/odometry/out",
        "mavros/odometry/in",
        "mavros/local_position/odom",
        "planning/pos_cmd",
    )
)

FRAMES = tuple(
    [
        f"uav{uav}_{suffix}"
        for uav in (1, 2)
        for suffix in (
            "map",
            "odom",
            "camera_init",
            "body",
            "base_link",
            "lidar",
            "odom_ned",
            "map_ned",
            "base_link_frd",
        )
    ]
    + ["world", "map", "base_link", "camera_link", "camera_init", "body", "imu"]
)

GENERIC_FRAMES = ("world", "map", "base_link", "camera_init", "body", "imu")

TRANSFORMS = tuple(
    [
        (f"uav{uav}_{parent}", f"uav{uav}_{child}", False)
        for uav in (1, 2)
        for parent, child in (
            ("map", "odom"),
            ("odom", "camera_init"),
            ("camera_init", "body"),
            ("body", "base_link"),
            ("base_link", "lidar"),
            ("odom", "odom_ned"),
            ("map", "map_ned"),
            ("base_link", "base_link_frd"),
        )
    ]
    + [
        ("uav1_camera_init", "uav2_camera_init", True),
        ("uav1_map", "uav2_map", True),
        ("uav1_body", "uav2_body", True),
    ]
)


def _round(value, digits=3):
    return None if value is None else round(float(value), digits)


def _uav_for_topic(topic):
    if topic.startswith("/uav1/"):
        return "uav1"
    if topic.startswith("/uav2/"):
        return "uav2"
    return None


def _expected_headers(topic):
    uav = _uav_for_topic(topic)
    if uav is None:
        return None
    suffix = topic.split(f"/{uav}/", 1)[1]
    contracts = {
        "rflysim/lidar": (f"{uav}_lidar", "N/A", False),
        "rflysim/imu": ("imu", "N/A", True),
        "slam/odometry_raw": ("camera_init", "body", True),
        "slam/cloud_registered": ("camera_init", "N/A", True),
        "slam/cloud_registered_body": ("body", "N/A", True),
        "mavros/odometry/out": (f"{uav}_camera_init", f"{uav}_body", False),
        "mavros/odometry/in": (f"{uav}_map", f"{uav}_base_link", False),
        "mavros/local_position/odom": ("map", "base_link", True),
        "planning/pos_cmd": ("world", "N/A", True),
    }
    return contracts.get(suffix)


def classify_headers(topic, frame_id, child_frame_id):
    """Classify labels against the verified current contract without gating."""
    findings = []
    own_uav = _uav_for_topic(topic)
    other_uav = "uav2" if own_uav == "uav1" else "uav1"
    for field, value in (
        ("header.frame_id", frame_id),
        ("child_frame_id", child_frame_id),
    ):
        if own_uav and isinstance(value, str) and value.startswith(f"{other_uav}_"):
            findings.append(
                {
                    "severity": "ERROR",
                    "category": "CROSS_UAV_FRAME_LABEL",
                    "field": field,
                    "observed": value,
                    "detail": f"{own_uav} topic reports a {other_uav} frame label",
                }
            )

    expected = _expected_headers(topic)
    if expected is None or frame_id == "N/A":
        return findings
    expected_frame, expected_child, legacy = expected
    mismatches = []
    if frame_id != expected_frame:
        mismatches.append(
            {"field": "header.frame_id", "expected": expected_frame, "observed": frame_id}
        )
    if expected_child != "N/A" and child_frame_id != expected_child:
        mismatches.append(
            {"field": "child_frame_id", "expected": expected_child, "observed": child_frame_id}
        )
    for mismatch in mismatches:
        findings.append(
            {
                "severity": "WARNING",
                "category": "HEADER_CONTRACT_MISMATCH",
                **mismatch,
            }
        )
    if legacy and not mismatches:
        findings.append(
            {
                "severity": "INFO",
                "category": "LEGACY_GENERIC_LABEL",
                "observed": {
                    "header.frame_id": frame_id,
                    "child_frame_id": child_frame_id,
                },
                "detail": "matches the verified protected-baseline label contract",
            }
        )
    return findings


def build_topic_report(
    topic,
    *,
    advertised,
    message_type=None,
    publishers=(),
    subscribers=(),
    samples=(),
    timestamp_warn_ms=2000.0,
    subscription_error=None,
    advertised_at_s=None,
    subscribed_at_s=None,
    graph_observations=(),
):
    """Reduce normalized message samples to a compact topic report."""
    samples = list(samples)
    result = {
        "topic": topic,
        "message_type": message_type or "UNKNOWN",
        "publishers": sorted(set(publishers)),
        "subscribers": sorted(set(subscribers)),
        "header_frame_id": "N/A",
        "header.frame_id": "N/A",
        "child_frame_id": "N/A",
        "header_stamp": "N/A",
        "header.stamp": "N/A",
        "arrival_time": "N/A",
        "age_ms": {"minimum": None, "maximum": None, "mean": None},
        "interarrival_gap_ms": {"minimum": None, "maximum": None, "mean": None},
        "sample_count": len(samples),
        "observed_frequency_hz": None,
        "first_sample": None,
        "last_sample": None,
        "observed_frame_ids": [],
        "observed_child_frame_ids": [],
        "header_findings": [],
        "timestamp_findings": [],
        "status": "NOT_ADVERTISED",
        "advertised_at_s": advertised_at_s,
        "subscribed_at_s": subscribed_at_s,
        "graph_observations": list(graph_observations),
    }
    if subscription_error:
        result["subscription_error"] = subscription_error
    if not advertised:
        return result
    if subscription_error:
        result["status"] = "TYPE_UNAVAILABLE"
        return result
    if not samples:
        result["status"] = "NO_MESSAGE"
        return result

    first = dict(samples[0])
    last = dict(samples[-1])
    result.update(
        {
            "status": "OBSERVED",
            "header_frame_id": last.get("header_frame_id", "N/A"),
            "header.frame_id": last.get("header_frame_id", "N/A"),
            "child_frame_id": last.get("child_frame_id", "N/A"),
            "header_stamp": last.get("header_stamp", "N/A"),
            "header.stamp": last.get("header_stamp", "N/A"),
            "arrival_time": last.get("arrival_time", "N/A"),
            "first_sample": first,
            "last_sample": last,
            "observed_frame_ids": sorted(
                {
                    item.get("header_frame_id", "N/A")
                    for item in samples
                    if item.get("header_frame_id", "N/A") != "N/A"
                }
            ),
            "observed_child_frame_ids": sorted(
                {
                    item.get("child_frame_id", "N/A")
                    for item in samples
                    if item.get("child_frame_id", "N/A") != "N/A"
                }
            ),
        }
    )
    arrivals = [float(item["arrival_time"]) for item in samples]
    if len(arrivals) >= 2 and arrivals[-1] > arrivals[0]:
        result["observed_frequency_hz"] = _round(
            (len(arrivals) - 1) / (arrivals[-1] - arrivals[0])
        )
        gaps = [
            (right - left) * 1000.0
            for left, right in zip(arrivals, arrivals[1:])
        ]
        result["interarrival_gap_ms"] = {
            "minimum": _round(min(gaps)),
            "maximum": _round(max(gaps)),
            "mean": _round(sum(gaps) / len(gaps)),
        }
    ages = []
    zero_stamps = 0
    for item in samples:
        stamp = item.get("header_stamp", "N/A")
        if isinstance(stamp, (int, float)):
            if float(stamp) == 0.0:
                zero_stamps += 1
            else:
                ages.append((float(item["arrival_time"]) - float(stamp)) * 1000.0)
    if ages:
        result["age_ms"] = {
            "minimum": _round(min(ages)),
            "maximum": _round(max(ages)),
            "mean": _round(sum(ages) / len(ages)),
        }
        if max(abs(value) for value in ages) > float(timestamp_warn_ms):
            result["timestamp_findings"].append(
                {
                    "severity": "WARNING",
                    "category": "TIMESTAMP_AGE",
                    "threshold_ms": float(timestamp_warn_ms),
                    "detail": "at least one message age exceeds the configured magnitude threshold",
                }
            )
    if zero_stamps:
        result["timestamp_findings"].append(
            {
                "severity": "WARNING",
                "category": "ZERO_HEADER_STAMP",
                "sample_count": zero_stamps,
            }
        )
    finding_groups = {}
    for item in samples:
        arrival = item.get("arrival_time")
        for finding in classify_headers(
            topic,
            item.get("header_frame_id", "N/A"),
            item.get("child_frame_id", "N/A"),
        ):
            key = json.dumps(finding, sort_keys=True)
            grouped = finding_groups.get(key)
            if grouped is None:
                grouped = {
                    **finding,
                    "occurrence_count": 0,
                    "first_arrival_time": arrival,
                    "last_arrival_time": arrival,
                }
                finding_groups[key] = grouped
            grouped["occurrence_count"] += 1
            grouped["last_arrival_time"] = arrival
    result["header_findings"] = list(finding_groups.values())
    return result


def build_generic_frame_usage(topics):
    usage = {}
    for frame in GENERIC_FRAMES:
        used_by = []
        for topic, topic_report in sorted(topics.items()):
            if frame in topic_report.get("observed_frame_ids", []):
                used_by.append({"topic": topic, "field": "header.frame_id"})
            if frame in topic_report.get("observed_child_frame_ids", []):
                used_by.append({"topic": topic, "field": "child_frame_id"})
        uavs = sorted({_uav_for_topic(item["topic"]) for item in used_by if _uav_for_topic(item["topic"])})
        usage[frame] = {
            "used_by": used_by,
            "uavs": uavs,
            "status": "GENERIC_FRAME_REUSE" if len(uavs) > 1 else ("USED" if used_by else "NOT_OBSERVED"),
            "classification": "MESSAGE_LABEL_USAGE",
        }
    return usage


def find_cross_uav_topic_edges(topics):
    edges = []
    for topic, topic_report in sorted(topics.items()):
        source_uav = _uav_for_topic(topic)
        other_uav = "uav2" if source_uav == "uav1" else "uav1"
        if source_uav is None:
            continue
        for endpoint_kind, status in (
            ("publishers", "CROSS_UAV_PUBLISHER"),
            ("subscribers", "CROSS_UAV_SUBSCRIBER"),
        ):
            for endpoint in topic_report.get(endpoint_kind, []):
                if endpoint != f"/{other_uav}" and not endpoint.startswith(f"/{other_uav}/"):
                    continue
                edges.append(
                    {
                        "status": status,
                        "topic": topic,
                        "source_uav": source_uav,
                        "endpoint": endpoint,
                        "endpoint_kind": endpoint_kind[:-1],
                        "severity": "WARNING",
                    }
                )
    return edges


def newly_advertised_topics(published_types, subscribed_topics, subscription_errors):
    """Return required topics that can now receive their first subscription."""
    return sorted(
        topic
        for topic in TOPICS
        if topic in published_types
        and topic not in subscribed_topics
        and topic not in subscription_errors
    )


def merge_graph_observations(topic, observations, observer_node):
    """Retain start/end graph truth while removing this probe from endpoints."""
    normalized = []
    publishers = set()
    subscribers = set()
    for observation in observations:
        item = {
            "label": observation["label"],
            "timestamp": observation["timestamp"],
            "publishers": sorted(
                node for node in observation.get("publishers", []) if node != observer_node
            ),
            "subscribers": sorted(
                node for node in observation.get("subscribers", []) if node != observer_node
            ),
        }
        normalized.append(item)
        publishers.update(item["publishers"])
        subscribers.update(item["subscribers"])
    return {
        "topic": topic,
        "publishers": sorted(publishers),
        "subscribers": sorted(subscribers),
        "graph_observations": normalized,
        "observer_node_filtered": observer_node,
    }


def build_tf_topology_checks(tf_edges):
    parents_by_child = {}
    duplicate_broadcasters = []
    direct_cross_edges = []
    for edge in tf_edges.values():
        parents_by_child.setdefault(edge["child"], set()).add(edge["parent"])
        if len(edge["broadcasters"]) > 1:
            duplicate_broadcasters.append(
                {
                    "parent": edge["parent"],
                    "child": edge["child"],
                    "broadcasters": edge["broadcasters"],
                }
            )
        parent_uav = "uav1" if edge["parent"].startswith("uav1_") else (
            "uav2" if edge["parent"].startswith("uav2_") else None
        )
        child_uav = "uav1" if edge["child"].startswith("uav1_") else (
            "uav2" if edge["child"].startswith("uav2_") else None
        )
        if parent_uav and child_uav and parent_uav != child_uav:
            direct_cross_edges.append(
                {
                    "status": "CROSS_UAV_TRANSFORM_PRESENT",
                    "parent": edge["parent"],
                    "child": edge["child"],
                    "broadcasters": edge["broadcasters"],
                    "kind": "DIRECT_TF_EDGE",
                }
            )
    return {
        "multiple_parent_children": [
            {"child": child, "parents": sorted(parents)}
            for child, parents in sorted(parents_by_child.items())
            if len(parents) > 1
        ],
        "duplicate_tf_broadcasters": duplicate_broadcasters,
        "direct_cross_uav_edges": direct_cross_edges,
    }


def build_transform_report(parent, child, observation=None, cross_uav=False, detail=None):
    result = {
        "parent": parent,
        "child": child,
        "cross_uav": bool(cross_uav),
        "status": "NO_TRANSFORM",
        "severity": "INFO" if cross_uav else "WARNING",
        "translation": None,
        "rotation": None,
        "lookup_timestamp": None,
        "direct_edge_observed": False,
        "broadcasters": [],
    }
    if detail:
        result["detail"] = detail
    if observation is None:
        return result
    result.update(
        {
            "status": "CROSS_UAV_TRANSFORM_PRESENT" if cross_uav else "TRANSFORM_PRESENT",
            "severity": "WARNING" if cross_uav else "INFO",
            "translation": observation.get("translation"),
            "rotation": observation.get("rotation"),
            "lookup_timestamp": observation.get("lookup_timestamp"),
            "direct_edge_observed": bool(observation.get("direct_edge_observed", False)),
            "broadcasters": sorted(set(observation.get("broadcasters", []))),
        }
    )
    return result


def build_summary(report):
    topics = report.get("topics", {})
    transforms = report.get("transforms", {})
    generic = report.get("generic_frame_usage", {})
    statuses = [item.get("status") for item in topics.values()]
    header_findings = [
        finding
        for item in topics.values()
        for finding in item.get("header_findings", [])
    ]
    timestamp_findings = [
        finding
        for item in topics.values()
        for finding in item.get("timestamp_findings", [])
    ]
    return {
        "topics_expected": len(TOPICS),
        "topics_observed": sum(status == "OBSERVED" for status in statuses),
        "topics_missing": sum(status == "NOT_ADVERTISED" for status in statuses),
        "topics_no_message": sum(status == "NO_MESSAGE" for status in statuses),
        "generic_frame_labels_detected": sorted(
            frame for frame, item in generic.items() if item.get("status") == "GENERIC_FRAME_REUSE"
        ),
        "cross_uav_topic_edges": len(report.get("cross_uav_checks", {}).get("topic_edges", [])),
        "cross_uav_tf_edges": len(report.get("cross_uav_checks", {}).get("tf_edges", [])),
        "tf_lookup_success": sum(
            item.get("status") in ("TRANSFORM_PRESENT", "CROSS_UAV_TRANSFORM_PRESENT")
            for item in transforms.values()
        ),
        "tf_lookup_failed": sum(item.get("status") == "NO_TRANSFORM" for item in transforms.values()),
        "tf_expected_lookup_failed": sum(
            item.get("status") == "NO_TRANSFORM" and not item.get("cross_uav")
            for item in transforms.values()
        ),
        "cross_uav_tf_absent": sum(
            item.get("status") == "NO_TRANSFORM" and item.get("cross_uav")
            for item in transforms.values()
        ),
        "cross_uav_tf_present": sum(
            item.get("status") == "CROSS_UAV_TRANSFORM_PRESENT"
            for item in transforms.values()
        ),
        "header_mismatch_findings": sum(
            item.get("category") in ("HEADER_CONTRACT_MISMATCH", "CROSS_UAV_FRAME_LABEL")
            for item in header_findings
        ),
        "legacy_generic_label_findings": sum(
            item.get("category") == "LEGACY_GENERIC_LABEL" for item in header_findings
        ),
        "timestamp_warnings": sum(item.get("severity") == "WARNING" for item in timestamp_findings),
        "multiple_parent_findings": len(
            report.get("cross_uav_checks", {}).get("multiple_parent_children", [])
        ),
        "duplicate_tf_broadcaster_findings": len(
            report.get("cross_uav_checks", {}).get("duplicate_tf_broadcasters", [])
        ),
    }


def _markdown_value(value):
    if value is None:
        return "N/A"
    if isinstance(value, (dict, list)):
        return f"`{json.dumps(value, sort_keys=True)}`"
    return str(value).replace("|", "\\|")


def render_markdown(report):
    metadata = report.get("metadata", {})
    summary = report.get("summary", {})
    lines = [
        "# Dual-UAV TF / Frame Contract Probe",
        "",
        "> Read-only observation. Transform presence is evidence, not a correctness verdict.",
        "",
        "## Metadata",
        "",
    ]
    lines.extend(f"- {key}: {_markdown_value(value)}" for key, value in sorted(metadata.items()))
    lines.extend(["", "## Summary", ""])
    lines.extend(f"- {key}: {_markdown_value(value)}" for key, value in sorted(summary.items()))
    lines.extend(
        [
            "",
            "## Topics",
            "",
            "| Topic | Status | Type | Publishers | Subscribers | Frame | Child | Samples | Hz | Age ms (min/mean/max) | Gap ms (min/mean/max) |",
            "| --- | --- | --- | --- | --- | --- | --- | ---: | ---: | --- | --- |",
        ]
    )
    for topic, item in sorted(report.get("topics", {}).items()):
        age = item.get("age_ms", {})
        age_text = f"{age.get('minimum')}/{age.get('mean')}/{age.get('maximum')}"
        gap = item.get("interarrival_gap_ms", {})
        gap_text = f"{gap.get('minimum')}/{gap.get('mean')}/{gap.get('maximum')}"
        lines.append(
            "| "
            + " | ".join(
                _markdown_value(value)
                for value in (
                    topic,
                    item.get("status"),
                    item.get("message_type"),
                    item.get("publishers", []),
                    item.get("subscribers", []),
                    item.get("header_frame_id"),
                    item.get("child_frame_id"),
                    item.get("sample_count"),
                    item.get("observed_frequency_hz"),
                    age_text,
                    gap_text,
                )
            )
            + " |"
        )
    lines.extend(
        [
            "",
            "## Transform Lookups",
            "",
            "| Parent | Child | Status | Translation | Rotation | Lookup stamp | Direct | Broadcasters |",
            "| --- | --- | --- | --- | --- | --- | --- | --- |",
        ]
    )
    for item in report.get("transforms", {}).values():
        lines.append(
            "| "
            + " | ".join(
                _markdown_value(item.get(key))
                for key in (
                    "parent",
                    "child",
                    "status",
                    "translation",
                    "rotation",
                    "lookup_timestamp",
                    "direct_edge_observed",
                    "broadcasters",
                )
            )
            + " |"
        )
    lines.extend(["", "## Observed TF Broadcasters", ""])
    tf_edges = report.get("tf_observations", {})
    if tf_edges:
        for edge, item in sorted(tf_edges.items()):
            lines.append(
                f"- `{edge}`: broadcasters={_markdown_value(item.get('broadcasters', []))}, "
                f"streams={_markdown_value(item.get('streams', []))}, samples={item.get('sample_count', 0)}"
            )
    else:
        lines.append("- No TF messages observed.")
    lines.extend(["", "## Generic Frame Usage", ""])
    for frame, item in sorted(report.get("generic_frame_usage", {}).items()):
        lines.append(f"- `{frame}`: {item.get('status')} — {_markdown_value(item.get('used_by', []))}")
    lines.extend(["", "## Cross-UAV / TF Topology Checks", ""])
    cross = report.get("cross_uav_checks", {})
    for key in ("topic_edges", "tf_edges", "multiple_parent_children", "duplicate_tf_broadcasters"):
        lines.append(f"- {key}: {_markdown_value(cross.get(key, []))}")
    lines.append("")
    return "\n".join(lines)


def write_reports(report, output_dir):
    output_dir = Path(output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)
    json_path = output_dir / "report.json"
    markdown_path = output_dir / "report.md"
    json_path.write_text(json.dumps(report, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    markdown_path.write_text(render_markdown(report), encoding="utf-8")
    return {"json": json_path, "markdown": markdown_path}


def _git_value(project_root, *args):
    try:
        completed = subprocess.run(
            ["git", *args],
            cwd=str(project_root),
            check=True,
            stdout=subprocess.PIPE,
            stderr=subprocess.DEVNULL,
            text=True,
            timeout=3.0,
        )
        return completed.stdout.strip()
    except (OSError, subprocess.SubprocessError):
        return "UNKNOWN"


class RosProbe:
    """ROS adapter. Every interaction is a subscription or read-only lookup."""

    def __init__(self, duration, timestamp_warn_ms, tf_timeout):
        try:
            import roslib.message
            import rospy
            import tf2_ros
            from tf2_msgs.msg import TFMessage
        except ImportError as exc:
            raise RuntimeError(f"ROS probe requires rospy, roslib, tf2_ros and tf2_msgs: {exc}") from exc
        self.rospy = rospy
        self.roslib_message = roslib.message
        self.tf2_ros = tf2_ros
        self.TFMessage = TFMessage
        self.duration = float(duration)
        self.timestamp_warn_ms = float(timestamp_warn_ms)
        self.tf_timeout = float(tf_timeout)
        self.lock = threading.Lock()
        self.samples = {topic: [] for topic in TOPICS}
        self.subscriptions = []
        self.subscribed_topics = set()
        self.subscription_errors = {}
        self.advertised_types = {}
        self.advertised_at_s = {}
        self.subscribed_at_s = {}
        self.tf_edges = {}
        if not rospy.core.is_initialized():
            rospy.init_node("frame_contract_probe", anonymous=True, disable_signals=True)
        self.buffer = tf2_ros.Buffer(cache_time=rospy.Duration(max(10.0, self.duration + 2.0)))
        self.listener = tf2_ros.TransformListener(self.buffer)

    def _graph(self):
        code, message, state = self.rospy.get_master().getSystemState()
        if code != 1:
            raise RuntimeError(f"cannot inspect ROS graph: {message}")
        publishers, subscribers, _services = state
        return (
            {topic: sorted(nodes) for topic, nodes in publishers},
            {topic: sorted(nodes) for topic, nodes in subscribers},
        )

    def _published_types(self):
        return {topic: message_type for topic, message_type in self.rospy.get_published_topics()}

    @staticmethod
    def _message_sample(message, arrival_time):
        header = getattr(message, "header", None)
        if header is None:
            frame_id = "N/A"
            header_stamp = "N/A"
        else:
            frame_id = str(getattr(header, "frame_id", "")) or "N/A"
            stamp = getattr(header, "stamp", None)
            header_stamp = float(stamp.to_sec()) if stamp is not None else "N/A"
        child = getattr(message, "child_frame_id", None)
        return {
            "header_frame_id": frame_id,
            "child_frame_id": str(child) if child not in (None, "") else "N/A",
            "header_stamp": header_stamp,
            "arrival_time": float(arrival_time),
        }

    def _topic_callback(self, message, topic):
        sample = self._message_sample(message, self.rospy.Time.now().to_sec())
        with self.lock:
            self.samples[topic].append(sample)

    def _tf_callback(self, message, stream):
        connection = getattr(message, "_connection_header", {}) or {}
        broadcaster = connection.get("callerid", "UNKNOWN")
        with self.lock:
            for transform in message.transforms:
                parent = str(transform.header.frame_id).lstrip("/")
                child = str(transform.child_frame_id).lstrip("/")
                edge_key = f"{parent} -> {child}"
                edge = self.tf_edges.setdefault(
                    edge_key,
                    {
                        "parent": parent,
                        "child": child,
                        "broadcasters": set(),
                        "streams": set(),
                        "sample_count": 0,
                        "first_stamp": None,
                        "last_stamp": None,
                    },
                )
                stamp = float(transform.header.stamp.to_sec())
                edge["broadcasters"].add(broadcaster)
                edge["streams"].add(stream)
                edge["sample_count"] += 1
                edge["first_stamp"] = stamp if edge["first_stamp"] is None else edge["first_stamp"]
                edge["last_stamp"] = stamp

    def _subscribe_tf(self):
        self.subscriptions.extend(
            [
                self.rospy.Subscriber("/tf", self.TFMessage, self._tf_callback, callback_args="/tf", queue_size=100),
                self.rospy.Subscriber(
                    "/tf_static", self.TFMessage, self._tf_callback, callback_args="/tf_static", queue_size=100
                ),
            ]
        )

    def _subscribe_new_topics(self, published_types, elapsed_s):
        for topic, message_type in published_types.items():
            if topic in TOPICS and topic not in self.advertised_at_s:
                self.advertised_at_s[topic] = _round(elapsed_s, 6)
        self.advertised_types.update(
            {topic: message_type for topic, message_type in published_types.items() if topic in TOPICS}
        )
        for topic in newly_advertised_topics(
            published_types, self.subscribed_topics, set(self.subscription_errors)
        ):
            message_type = published_types[topic]
            message_class = self.roslib_message.get_message_class(message_type)
            if message_class is None:
                self.subscription_errors[topic] = f"cannot resolve message class {message_type}"
                continue
            self.subscriptions.append(
                self.rospy.Subscriber(
                    topic, message_class, self._topic_callback, callback_args=topic, queue_size=20
                )
            )
            self.subscribed_topics.add(topic)
            self.subscribed_at_s[topic] = _round(elapsed_s, 6)

    def _normalized_tf_edges(self):
        normalized = {}
        with self.lock:
            items = list(self.tf_edges.items())
        for edge_key, edge in items:
            normalized[edge_key] = {
                **{key: value for key, value in edge.items() if key not in ("broadcasters", "streams")},
                "broadcasters": sorted(edge["broadcasters"]),
                "streams": sorted(edge["streams"]),
            }
        return normalized

    def _lookup(self, parent, child, cross_uav, tf_edges):
        direct = tf_edges.get(f"{parent} -> {child}")
        try:
            transform = self.buffer.lookup_transform(
                parent,
                child,
                self.rospy.Time(0),
                self.rospy.Duration(self.tf_timeout),
            )
        except Exception as exc:
            return build_transform_report(parent, child, None, cross_uav, detail=str(exc))
        translation = transform.transform.translation
        rotation = transform.transform.rotation
        observation = {
            "translation": {
                "x": _round(translation.x, 9),
                "y": _round(translation.y, 9),
                "z": _round(translation.z, 9),
            },
            "rotation": {
                "x": _round(rotation.x, 9),
                "y": _round(rotation.y, 9),
                "z": _round(rotation.z, 9),
                "w": _round(rotation.w, 9),
            },
            "lookup_timestamp": _round(transform.header.stamp.to_sec(), 9),
            "direct_edge_observed": direct is not None,
            "broadcasters": direct.get("broadcasters", []) if direct else [],
        }
        return build_transform_report(parent, child, observation, cross_uav)

    def collect(self, project_root):
        started_at = datetime.now(timezone.utc)
        monotonic_start = time.monotonic()
        initial_types = self._published_types()
        initial_publishers, initial_subscribers = self._graph()
        self._subscribe_tf()
        self._subscribe_new_topics(initial_types, 0.0)
        deadline = monotonic_start + self.duration
        next_topic_refresh = monotonic_start + 0.2
        while time.monotonic() < deadline and not self.rospy.is_shutdown():
            now = time.monotonic()
            if now >= next_topic_refresh:
                self._subscribe_new_topics(self._published_types(), now - monotonic_start)
                next_topic_refresh = now + 0.2
            time.sleep(min(0.05, max(0.0, deadline - time.monotonic())))
        actual_elapsed_s = time.monotonic() - monotonic_start
        final_types = self._published_types()
        self._subscribe_new_topics(final_types, actual_elapsed_s)
        final_publishers, final_subscribers = self._graph()
        published_types = {**self.advertised_types, **final_types}
        with self.lock:
            samples = {topic: list(values) for topic, values in self.samples.items()}
        topics = {}
        observer_node = self.rospy.get_name()
        for topic in TOPICS:
            graph = merge_graph_observations(
                topic,
                [
                    {
                        "label": "start",
                        "timestamp": 0.0,
                        "publishers": initial_publishers.get(topic, []),
                        "subscribers": initial_subscribers.get(topic, []),
                    },
                    {
                        "label": "end",
                        "timestamp": _round(actual_elapsed_s, 6),
                        "publishers": final_publishers.get(topic, []),
                        "subscribers": final_subscribers.get(topic, []),
                    },
                ],
                observer_node,
            )
            topics[topic] = build_topic_report(
                topic,
                advertised=topic in published_types,
                message_type=published_types.get(topic),
                publishers=graph["publishers"],
                subscribers=graph["subscribers"],
                samples=samples[topic],
                timestamp_warn_ms=self.timestamp_warn_ms,
                subscription_error=self.subscription_errors.get(topic),
                advertised_at_s=self.advertised_at_s.get(topic),
                subscribed_at_s=self.subscribed_at_s.get(topic),
                graph_observations=graph["graph_observations"],
            )
        tf_edges = self._normalized_tf_edges()
        transforms = {}
        for parent, child, cross_uav in TRANSFORMS:
            key = f"{parent} -> {child}"
            transforms[key] = self._lookup(parent, child, cross_uav, tf_edges)
        seen_frames = {
            frame
            for edge in tf_edges.values()
            for frame in (edge["parent"], edge["child"])
        }
        frames = {
            frame: {
                "status": "PRESENT" if frame in seen_frames else "NOT_OBSERVED",
                "observed_as_parent": any(edge["parent"] == frame for edge in tf_edges.values()),
                "observed_as_child": any(edge["child"] == frame for edge in tf_edges.values()),
            }
            for frame in FRAMES
        }
        topic_edges = find_cross_uav_topic_edges(topics)
        topology = build_tf_topology_checks(tf_edges)
        direct_cross_edges = topology["direct_cross_uav_edges"]
        lookup_cross_edges = [
            {
                "status": item["status"],
                "parent": item["parent"],
                "child": item["child"],
                "translation": item["translation"],
                "rotation": item["rotation"],
                "kind": "TF_LOOKUP_PATH",
            }
            for item in transforms.values()
            if item["status"] == "CROSS_UAV_TRANSFORM_PRESENT"
        ]
        cross_tf_edges = lookup_cross_edges + [
            edge for edge in direct_cross_edges if not any(
                item["parent"] == edge["parent"] and item["child"] == edge["child"]
                for item in lookup_cross_edges
            )
        ]
        report = {
            "metadata": {
                "timestamp": started_at.isoformat().replace("+00:00", "Z"),
                "completed_timestamp": datetime.now(timezone.utc).isoformat().replace("+00:00", "Z"),
                "hostname": socket.gethostname(),
                "ros_master_uri": os.environ.get("ROS_MASTER_URI", "UNKNOWN"),
                "git_commit": _git_value(project_root, "rev-parse", "HEAD"),
                "branch": _git_value(project_root, "branch", "--show-current"),
                "duration_s": self.duration,
                "actual_sampling_elapsed_s": _round(actual_elapsed_s, 6),
                "timestamp_warn_ms": self.timestamp_warn_ms,
                "tf_timeout_s": self.tf_timeout,
                "observer_node": observer_node,
                "mode": "READ_ONLY_OBSERVATION",
            },
            "topics": topics,
            "frames": frames,
            "transforms": transforms,
            "tf_observations": tf_edges,
            "generic_frame_usage": build_generic_frame_usage(topics),
            "cross_uav_checks": {
                "topic_edges": topic_edges,
                "tf_edges": cross_tf_edges,
                "multiple_parent_children": topology["multiple_parent_children"],
                "duplicate_tf_broadcasters": topology["duplicate_tf_broadcasters"],
            },
        }
        report["summary"] = build_summary(report)
        return report


def _default_project_root():
    return Path(__file__).resolve().parents[4]


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--duration", type=float, default=8.0, help="bounded sampling duration in seconds")
    parser.add_argument(
        "--timestamp-warn-ms",
        type=float,
        default=2000.0,
        help="conservative absolute message-age warning threshold; evidence only",
    )
    parser.add_argument("--tf-timeout", type=float, default=0.25, help="timeout per tf2 lookup in seconds")
    parser.add_argument(
        "--output-root",
        type=Path,
        default=None,
        help="root for a timestamped report directory (default: logs/frame_contract_probe)",
    )
    args = parser.parse_args(argv)
    if args.duration <= 0 or args.timestamp_warn_ms <= 0 or args.tf_timeout <= 0:
        parser.error("duration, timestamp-warn-ms, and tf-timeout must be positive")
    project_root = _default_project_root()
    output_root = args.output_root or project_root / "logs" / "frame_contract_probe"
    run_directory = output_root / datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%S.%fZ")
    try:
        report = RosProbe(args.duration, args.timestamp_warn_ms, args.tf_timeout).collect(project_root)
        paths = write_reports(report, run_directory)
    except Exception as exc:
        print(f"[ERROR] frame contract probe could not complete: {exc}", file=sys.stderr)
        return 2
    print(f"[INFO] JSON report: {paths['json']}")
    print(f"[INFO] Markdown report: {paths['markdown']}")
    print(json.dumps(report["summary"], indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
