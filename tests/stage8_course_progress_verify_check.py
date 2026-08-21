#!/usr/bin/env python3
"""Regression guard for course-progress fly-through verification.

Stage 8 live run showed that a radial-distance checkpoint verify can miss a
checkpoint the vehicle already passed while the executor was blocked on the
follower's verification.  When a verify action carries ``progress_mode:
course_s``, the executor must confirm by along-track arc length instead of
radial proximity to the goal point.
"""

from __future__ import annotations

import argparse
import importlib.util
import json
import sys
import threading
import time
from pathlib import Path
from types import SimpleNamespace


def load_executor(module_path):
    sys.path.insert(0, str(module_path.parent))
    spec = importlib.util.spec_from_file_location("mission_executor", str(module_path))
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def make_odom(x, y, z):
    return SimpleNamespace(
        pose=SimpleNamespace(
            pose=SimpleNamespace(position=SimpleNamespace(x=x, y=y, z=z)),
        ),
        twist=SimpleNamespace(
            twist=SimpleNamespace(
                linear=SimpleNamespace(x=0.3, y=0.0, z=0.0),
            )
        ),
    )


class FakeSubscriber:
    def __init__(self, topic, topic_type, callback, queue_size):
        self.topic = topic
        self.topic_type = topic_type
        self.callback = callback
        self.queue_size = queue_size


class FakeRospy:
    def __init__(self):
        self.subscribers = []

    def Subscriber(self, topic, topic_type, callback, queue_size=1):
        subscriber = FakeSubscriber(topic, topic_type, callback, queue_size)
        self.subscribers.append(subscriber)
        return subscriber

    def publish_odom(self, message):
        for subscriber in self.subscribers:
            if subscriber.topic == "/uav1/mavros/local_position/odom":
                subscriber.callback(message)

    def is_shutdown(self):
        return False


class DummyOdometry:
    pass


class DummyPositionCommand:
    pass


def verify_action(centreline, checkpoint_s=2.4, x=8.0, y=0.7, timeout_s=1.0):
    return {
        "sequence": 1,
        "stage": "collaborative_navigate",
        "action": "verify_planned_navigation",
        "uav": "uav1",
        "mavros_odom_topic": "/uav1/mavros/local_position/odom",
        "planner_cmd_topic": "/uav1/planning/pos_cmd",
        "goal": {"x": 4.9, "y": 0.7, "z": 1.0},
        "tolerance_m": 0.5,
        "timeout_s": timeout_s,
        "checkpoint_s": checkpoint_s,
        "progress_mode": "course_s",
        "progress_origin": [16.0, -0.7],
        "progress_centreline": centreline,
        "progress_tolerance_m": 0.1,
        "_odom_position": (x, y),
    }


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--executor-module", required=True, type=Path)
    parser.add_argument("--course-spec", required=True, type=Path)
    args = parser.parse_args()

    executor = load_executor(args.executor_module)
    course = json.loads(args.course_spec.read_text(encoding="utf-8"))
    centreline = course["centreline"]

    # Case 1: vehicle is 1.4 m PAST checkpoint s=2.4 (world x=24.0, s~=4.5).
    # The old radial check would fail; course_s progress must confirm instantly.
    backend = executor.RosBackend.__new__(executor.RosBackend)
    backend.rospy = FakeRospy()
    backend.Odometry = DummyOdometry
    backend.PositionCommand = DummyPositionCommand
    backend._topic_caches = {}
    action = verify_action(centreline)
    x, y = action.pop("_odom_position")
    publish_stop = threading.Event()

    def stream():
        while not publish_stop.is_set():
            backend.rospy.publish_odom(make_odom(x, y, 1.0))
            time.sleep(0.02)

    thread = threading.Thread(target=stream, daemon=True)
    thread.start()
    try:
        result = backend._verify_planned_navigation(action)
    finally:
        publish_stop.set()
        thread.join(timeout=2.0)
    assert result["status"] == "ros_navigation_success", result
    assert result["navigation"]["distance_m"] <= 0.0 + 1e-9

    # Case 2: vehicle still BEFORE the checkpoint (local x=3.0 -> world x=19.0,
    # s~=0.5) must not confirm.
    backend2 = executor.RosBackend.__new__(executor.RosBackend)
    backend2.rospy = FakeRospy()
    backend2.Odometry = DummyOdometry
    backend2.PositionCommand = DummyPositionCommand
    backend2._topic_caches = {}
    action2 = verify_action(centreline, x=3.0, y=0.7, timeout_s=0.5)
    x2, y2 = action2.pop("_odom_position")
    publish_stop2 = threading.Event()

    def stream2():
        while not publish_stop2.is_set():
            backend2.rospy.publish_odom(make_odom(x2, y2, 1.0))
            time.sleep(0.02)

    thread2 = threading.Thread(target=stream2, daemon=True)
    thread2.start()
    raised = False
    try:
        try:
            backend2._verify_planned_navigation(action2)
        except RuntimeError:
            raised = True
    finally:
        publish_stop2.set()
        thread2.join(timeout=2.0)
    assert raised, "verify must not confirm before the vehicle passes the checkpoint"

    print("stage8 course progress verify: PASS")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
