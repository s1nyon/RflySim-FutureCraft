#!/usr/bin/env python3
"""Regression guard for persistent navigation subscribers in mission_executor.

Live run ``stage7-20260807T124153Z-22785`` showed that repeatedly calling
``rospy.wait_for_message()`` inside ``_verify_planned_navigation()`` churns
temporary subscribers (ROS master logged ~60-70 ``+SUB``/``-SUB`` per second)
and eventually stalls odom/planner-command delivery for later goals.  This
check proves that consecutive navigation goals reuse one long-lived subscriber
per topic instead of creating a new one per goal.
"""

from __future__ import annotations

import argparse
import importlib.util
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


def make_message(x, y, z):
    return SimpleNamespace(
        pose=SimpleNamespace(
            pose=SimpleNamespace(
                position=SimpleNamespace(x=x, y=y, z=z),
            ),
        ),
    )


class FakeSubscriber:
    def __init__(self, topic, topic_type, callback, queue_size):
        self.topic = topic
        self.topic_type = topic_type
        self.callback = callback
        self.queue_size = queue_size
        self.active = True

    def unregister(self):
        self.active = False

    def __enter__(self):
        return self

    def __exit__(self, *_args):
        self.unregister()


class FakeRospy:
    def __init__(self):
        self.subscribers = []
        self.published_planner = 0
        self.published_odom = 0

    def Subscriber(self, topic, topic_type, callback, queue_size=1):
        subscriber = FakeSubscriber(topic, topic_type, callback, queue_size)
        self.subscribers.append(subscriber)
        return subscriber

    def publish_odom(self, message):
        self.published_odom += 1
        for subscriber in self.subscribers:
            if subscriber.topic == "/uav1/mavros/local_position/odom":
                subscriber.callback(message)

    def publish_planner(self, message):
        self.published_planner += 1
        for subscriber in self.subscribers:
            if subscriber.topic == "/uav1/planning/pos_cmd":
                subscriber.callback(message)

    def is_shutdown(self):
        return False


class DummyOdometry:
    pass


class DummyPositionCommand:
    pass


def goal_action(sequence, x, y):
    return {
        "sequence": sequence,
        "stage": "collaborative_navigate",
        "action": "verify_planned_navigation",
        "uav": "uav1",
        "mavros_odom_topic": "/uav1/mavros/local_position/odom",
        "planner_cmd_topic": "/uav1/planning/pos_cmd",
        "goal": {"x": x, "y": y, "z": 1.0},
        "tolerance_m": 0.3,
        "timeout_s": 2.0,
    }


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--executor-module", required=True, type=Path)
    args = parser.parse_args()

    executor = load_executor(args.executor_module)
    backend = executor.RosBackend.__new__(executor.RosBackend)
    backend.rospy = FakeRospy()
    backend.Odometry = DummyOdometry
    backend.PositionCommand = DummyPositionCommand
    backend._topic_caches = {}

    goals = [(2.5, 0.7), (7.0, 0.7), (7.9, 1.6), (7.9, 4.7), (8.8, 5.6)]
    results = []
    # Simulate the live topic streams: MAVROS publishes odometry continuously
    # and EGO publishes PositionCommand while navigating.  A background thread
    # keeps both topics flowing so the persistent subscriber (created on first
    # verify) never starves, matching production behavior.
    publish_stop = threading.Event()
    current_goal = {"x": goals[0][0], "y": goals[0][1]}

    def stream_publisher():
        try:
            while not publish_stop.is_set():
                backend.rospy.publish_odom(
                    make_message(current_goal["x"], current_goal["y"], 1.0)
                )
                backend.rospy.publish_planner(make_message(0.0, 0.0, 1.0))
                time.sleep(0.02)
        except Exception:
            pass

    publisher_thread = threading.Thread(target=stream_publisher, daemon=True)
    publisher_thread.start()
    for index, (gx, gy) in enumerate(goals, start=1):
        current_goal["x"] = gx
        current_goal["y"] = gy
        deadline = time.monotonic() + 5.0
        confirmed = False
        while time.monotonic() < deadline and not confirmed:
            try:
                result = backend._verify_planned_navigation(goal_action(index, gx, gy))
                results.append(result)
                confirmed = True
                break
            except Exception:
                continue
        if not confirmed:
            raise AssertionError(f"goal {index} ({gx}, {gy}) did not verify within the deadline")
    publish_stop.set()
    publisher_thread.join(timeout=2.0)

    assert len(results) == len(goals)
    for index, result in enumerate(results, start=1):
        assert result["status"] == "ros_navigation_success", result
        assert result["navigation"]["distance_m"] <= 0.3, result

    odom_subscribers = [
        subscriber
        for subscriber in backend.rospy.subscribers
        if subscriber.topic == "/uav1/mavros/local_position/odom"
    ]
    planner_subscribers = [
        subscriber
        for subscriber in backend.rospy.subscribers
        if subscriber.topic == "/uav1/planning/pos_cmd"
    ]
    assert len(odom_subscribers) == 1, (
        f"expected exactly one persistent odom subscriber across {len(goals)} goals, "
        f"got {len(odom_subscribers)}"
    )
    assert len(planner_subscribers) == 1, (
        f"expected exactly one persistent planner-command subscriber across {len(goals)} goals, "
        f"got {len(planner_subscribers)}"
    )
    assert len(backend._topic_caches) == 2, backend._topic_caches
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
