#!/usr/bin/env python3
"""Bounded, read-only ROS sensor/localization/planner evidence probe for V2."""

from __future__ import annotations

import argparse
import json
import math
import os
import socket
import statistics
import time
from pathlib import Path
from typing import Any, Dict, Iterable, List, Set, Tuple


TOPIC_SUFFIXES = {
    "lidar": "/uav{uav}/rflysim/lidar",
    "imu": "/uav{uav}/rflysim/imu",
    "slam_odom": "/uav{uav}/slam/odometry_raw",
    "slam_cloud": "/uav{uav}/slam/cloud_registered",
    "ego_cmd": "/uav{uav}/planning/pos_cmd",
}
RGB_CANDIDATES = {
    1: ["/rflysim/sensor1/img_rgb", "/uav1/rflysim/sensor1/img_rgb"],
    2: ["/rflysim/sensor11/img_rgb", "/uav2/rflysim/sensor11/img_rgb"],
}


def expected_topics() -> List[str]:
    values = [template.format(uav=uav) for uav in (1, 2) for template in TOPIC_SUFFIXES.values()]
    values.extend(topic for candidates in RGB_CANDIDATES.values() for topic in candidates)
    return values


def _topic_summary(records: List[Dict[str, Any]], advertised: bool, duration: float) -> Dict[str, Any]:
    if not advertised:
        return {"status": "NOT_ADVERTISED", "sample_count": 0, "frequency_hz": 0.0}
    if not records:
        return {"status": "NO_MESSAGE", "sample_count": 0, "frequency_hz": 0.0}
    arrivals = [float(item["arrival"]) for item in records]
    ages = [(float(item["arrival"]) - float(item["stamp"])) * 1000 for item in records if item.get("stamp") is not None]
    result = {"status": "OBSERVED", "sample_count": len(records), "frequency_hz": round((len(records) - 1) / max(arrivals[-1] - arrivals[0], 1e-9), 3) if len(records) > 1 else round(1.0 / duration, 3), "first": records[0], "last": records[-1]}
    if ages:
        result["age_ms"] = {"minimum": round(min(ages), 3), "maximum": round(max(ages), 3), "mean": round(statistics.mean(ages), 3)}
    return result


def build_report(expected: Iterable[str], samples: Dict[str, List[Dict[str, Any]]], advertised: Set[str], duration: float) -> Dict[str, Any]:
    topics = {topic: _topic_summary(samples.get(topic, []), topic in advertised, duration) for topic in expected}
    observed = sum(value["status"] == "OBSERVED" for value in topics.values())
    return {"metadata": {"probe": "competition_course_v2", "hostname": socket.gethostname(), "duration_sec": duration}, "topics": topics, "summary": {"topics_expected": len(topics), "topics_observed": observed, "topics_missing": len(topics) - observed, "not_advertised": sum(value["status"] == "NOT_ADVERTISED" for value in topics.values()), "no_message": sum(value["status"] == "NO_MESSAGE" for value in topics.values())}}


def write_reports(report: Dict[str, Any], output: Path) -> Tuple[Path, Path]:
    output.mkdir(parents=True, exist_ok=True); json_path, markdown_path = output / "report.json", output / "report.md"
    json_path.write_text(json.dumps(report, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    rows = ["# Competition Course V2 Live Probe", "", "Read-only bounded evidence; topic activity alone does not prove obstacle or ArUco visibility.", "", "| Topic | Status | Samples | Hz | Frame |", "| --- | --- | ---: | ---: | --- |"]
    for topic, value in sorted(report["topics"].items()):
        rows.append("| `{}` | {} | {} | {} | `{}` |".format(topic, value["status"], value["sample_count"], value["frequency_hz"], value.get("last", {}).get("frame_id", "N/A")))
    rows += ["", "## Summary", "", "```json", json.dumps(report["summary"], indent=2, sort_keys=True), "```", ""]
    markdown_path.write_text("\n".join(rows), encoding="utf-8"); return json_path, markdown_path


def _stamp(message) -> Any:
    header = getattr(message, "header", None); value = getattr(header, "stamp", None)
    if value is None: return None
    stamp = value.to_sec()
    return stamp if stamp > 0 else None


def _base_record(message, now: float) -> Dict[str, Any]:
    header = getattr(message, "header", None)
    return {"arrival": now, "stamp": _stamp(message), "frame_id": getattr(header, "frame_id", "N/A") if header else "N/A"}


def _save_image(message, path: Path) -> Dict[str, Any]:
    result = {"width": int(message.width), "height": int(message.height), "encoding": message.encoding, "step": int(message.step)}
    encoding = message.encoding.lower()
    if encoding not in ("rgb8", "bgr8", "mono8") or message.width <= 0 or message.height <= 0:
        result["saved"] = False; return result
    channels = 1 if encoding == "mono8" else 3; rows = []
    data = bytes(message.data)
    for row in range(message.height):
        value = data[row * message.step: row * message.step + message.width * channels]
        if encoding == "bgr8":
            value = b"".join(value[index:index + 3][::-1] for index in range(0, len(value), 3))
        rows.append(value)
    magic = b"P5" if channels == 1 else b"P6"; path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(magic + b"\n%d %d\n255\n" % (message.width, message.height) + b"".join(rows))
    result.update({"saved": True, "evidence_file": path.name, "byte_min": min(data) if data else None, "byte_max": max(data) if data else None})
    return result


def collect_ros(duration: float, image_dir: Path) -> Tuple[Dict[str, List[Dict[str, Any]]], Set[str]]:
    import rospy
    import sensor_msgs.point_cloud2 as pc2
    from nav_msgs.msg import Odometry
    from sensor_msgs.msg import Image, Imu, PointCloud2
    from quadrotor_msgs.msg import PositionCommand

    expected = expected_topics(); advertised = {name for name, _kind in rospy.get_published_topics()}; samples: Dict[str, List[Dict[str, Any]]] = {topic: [] for topic in expected}; saved_images: Set[str] = set()

    def callback(topic, kind):
        def receive(message):
            now = rospy.Time.now().to_sec(); record = _base_record(message, now)
            if kind == "cloud":
                points = []
                for point in pc2.read_points(message, field_names=("x", "y", "z"), skip_nans=True):
                    if all(math.isfinite(value) for value in point): points.append(point)
                    if len(points) >= 5000: break
                record["point_count"] = int(message.width * message.height)
                if points: record["finite_bounds"] = [round(function(point[index] for point in points), 4) for index in range(3) for function in (min, max)]
            elif kind == "image" and topic not in saved_images:
                record.update(_save_image(message, image_dir / (topic.strip("/").replace("/", "_") + ".ppm"))); saved_images.add(topic)
            samples[topic].append(record)
            if len(samples[topic]) > 200: samples[topic] = samples[topic][-200:]
        return receive

    subscriptions = []
    for uav in (1, 2):
        subscriptions += [rospy.Subscriber(TOPIC_SUFFIXES["lidar"].format(uav=uav), PointCloud2, callback(TOPIC_SUFFIXES["lidar"].format(uav=uav), "cloud"), queue_size=1), rospy.Subscriber(TOPIC_SUFFIXES["imu"].format(uav=uav), Imu, callback(TOPIC_SUFFIXES["imu"].format(uav=uav), "imu"), queue_size=20), rospy.Subscriber(TOPIC_SUFFIXES["slam_odom"].format(uav=uav), Odometry, callback(TOPIC_SUFFIXES["slam_odom"].format(uav=uav), "odom"), queue_size=10), rospy.Subscriber(TOPIC_SUFFIXES["slam_cloud"].format(uav=uav), PointCloud2, callback(TOPIC_SUFFIXES["slam_cloud"].format(uav=uav), "cloud"), queue_size=1), rospy.Subscriber(TOPIC_SUFFIXES["ego_cmd"].format(uav=uav), PositionCommand, callback(TOPIC_SUFFIXES["ego_cmd"].format(uav=uav), "command"), queue_size=10)]
        for topic in RGB_CANDIDATES[uav]: subscriptions.append(rospy.Subscriber(topic, Image, callback(topic, "image"), queue_size=1))
    rospy.sleep(duration)
    advertised.update(name for name, _kind in rospy.get_published_topics())
    advertised.update(topic for topic, records in samples.items() if records)
    for subscription in subscriptions: subscription.unregister()
    return samples, advertised


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__); parser.add_argument("--duration", type=float, default=8.0); parser.add_argument("--output", type=Path)
    args = parser.parse_args()
    if not math.isfinite(args.duration) or args.duration <= 0: parser.error("--duration must be positive")
    output = args.output or Path(os.environ.get("COMPETITION_COURSE_PROBE_OUTPUT", "logs/competition_course_v2_probe/{}".format(time.strftime("%Y%m%dT%H%M%SZ", time.gmtime()))))
    import rospy
    rospy.init_node("competition_course_v2_live_probe", anonymous=True, disable_signals=True)
    samples, advertised = collect_ros(args.duration, output / "images"); report = build_report(expected_topics(), samples, advertised, args.duration)
    report["metadata"].update({"timestamp_utc": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()), "ros_master_uri": os.environ.get("ROS_MASTER_URI", "")})
    json_path, markdown_path = write_reports(report, output); print(json.dumps({"json": str(json_path), "markdown": str(markdown_path), "summary": report["summary"]}, indent=2)); return 0


if __name__ == "__main__":
    raise SystemExit(main())
