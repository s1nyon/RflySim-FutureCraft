#!/usr/bin/env python3
"""Focused opt-in terminal-settle contract for the protected executor."""

from __future__ import annotations

import argparse
import importlib.util
import sys
import threading
import time
from pathlib import Path
from types import SimpleNamespace


def load_executor(path):
    sys.path.insert(0, str(path.parent))
    spec = importlib.util.spec_from_file_location("mission_executor_terminal", str(path))
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def odom(x=1.0, speed=0.0):
    return SimpleNamespace(
        pose=SimpleNamespace(pose=SimpleNamespace(position=SimpleNamespace(x=x, y=0.0, z=1.0))),
        twist=SimpleNamespace(twist=SimpleNamespace(linear=SimpleNamespace(x=speed, y=0.0, z=0.0))),
    )


class FakeSubscriber:
    def __init__(self, topic, callback):
        self.topic = topic
        self.callback = callback


class FakeRospy:
    def __init__(self):
        self.subscribers = []

    def Subscriber(self, topic, _topic_type, callback, queue_size=1):
        subscriber = FakeSubscriber(topic, callback)
        self.subscribers.append(subscriber)
        return subscriber

    def publish(self, topic, message):
        for subscriber in list(self.subscribers):
            if subscriber.topic == topic:
                subscriber.callback(message)

    def is_shutdown(self):
        return False


class DummyOdometry:
    pass


class DummyPositionCommand:
    pass


ODOM_TOPIC = "/uav1/mavros/local_position/odom"
PLANNER_TOPIC = "/uav1/planning/pos_cmd"


def action(timeout=0.4, settle=None, maximum_speed=None):
    result = {
        "sequence": 1,
        "stage": "terminal_settle",
        "action": "verify_planned_navigation",
        "uav": "uav1",
        "mavros_odom_topic": ODOM_TOPIC,
        "planner_cmd_topic": PLANNER_TOPIC,
        "goal": {"x": 1.0, "y": 0.0, "z": 1.0},
        "tolerance_m": 0.25,
        "timeout_s": timeout,
    }
    if settle is not None:
        result["settle_duration_s"] = settle
    if maximum_speed is not None:
        result["maximum_speed_mps"] = maximum_speed
    return result


def backend(executor):
    value = executor.RosBackend.__new__(executor.RosBackend)
    value.rospy = FakeRospy()
    value.Odometry = DummyOdometry
    value.PositionCommand = DummyPositionCommand
    value._topic_caches = {}
    return value


def run_stream(executor, samples, *, settle=None, maximum_speed=None, timeout=0.4, planner=True):
    value = backend(executor)
    stop = threading.Event()

    def stream():
        deadline = time.monotonic() + 1.0
        while len(value.rospy.subscribers) < 2 and time.monotonic() < deadline:
            time.sleep(0.001)
        for duration, message in samples:
            sample_deadline = time.monotonic() + duration
            while not stop.is_set() and time.monotonic() < sample_deadline:
                value.rospy.publish(ODOM_TOPIC, message)
                if planner:
                    value.rospy.publish(PLANNER_TOPIC, object())
                time.sleep(0.005)

    thread = threading.Thread(target=stream, daemon=True)
    thread.start()
    started = time.monotonic()
    try:
        result = value._verify_planned_navigation(
            action(timeout=timeout, settle=settle, maximum_speed=maximum_speed)
        )
        return result, time.monotonic() - started
    finally:
        stop.set()
        thread.join(timeout=1.0)


def expect_timeout(executor, samples, *, settle, maximum_speed, timeout):
    try:
        run_stream(
            executor,
            samples,
            settle=settle,
            maximum_speed=maximum_speed,
            timeout=timeout,
        )
    except RuntimeError as exc:
        assert "not confirmed" in str(exc)
    else:
        raise AssertionError("intermittent/insufficient settle must time out")


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--executor-module", required=True, type=Path)
    args = parser.parse_args()
    executor = load_executor(args.executor_module)

    legacy, legacy_elapsed = run_stream(executor, [(0.05, odom())])
    assert legacy["status"] == "ros_navigation_success"
    assert legacy_elapsed < 0.05, "legacy plan must retain immediate acceptance"

    stable, stable_elapsed = run_stream(
        executor,
        [(0.12, odom())],
        settle=0.06,
        maximum_speed=0.15,
    )
    assert stable_elapsed >= 0.055, stable_elapsed
    assert stable["navigation"]["settle_duration_s"] >= 0.06
    assert stable["navigation"]["planner_commands"] > 0

    speed_reset, speed_elapsed = run_stream(
        executor,
        [(0.035, odom()), (0.025, odom(speed=0.4)), (0.09, odom())],
        settle=0.06,
        maximum_speed=0.15,
    )
    assert speed_elapsed >= 0.105, speed_elapsed
    assert speed_reset["navigation"]["settle_reset_count"] >= 1

    position_reset, position_elapsed = run_stream(
        executor,
        [(0.035, odom()), (0.025, odom(x=1.5)), (0.09, odom())],
        settle=0.06,
        maximum_speed=0.15,
    )
    assert position_elapsed >= 0.105, position_elapsed
    assert position_reset["navigation"]["settle_reset_count"] >= 1

    expect_timeout(
        executor,
        [(0.03, odom()), (0.03, odom(speed=0.4)), (0.03, odom()), (0.03, odom(x=1.5))],
        settle=0.06,
        maximum_speed=0.15,
        timeout=0.13,
    )
    expect_timeout(
        executor,
        [(0.10, odom())],
        settle=0.20,
        maximum_speed=0.15,
        timeout=0.10,
    )

    invalid = action(settle=-1.0, maximum_speed=0.15)
    try:
        executor.validate_action(invalid)
    except ValueError as exc:
        assert "settle" in str(exc)
    else:
        raise AssertionError("negative settle duration must fail validation")

    event_action = action(settle=3.0, maximum_speed=0.15)
    event_result = {
        "status": "ros_navigation_success",
        "detail": "settled",
        "navigation": {
            "distance_m": 0.1,
            "planner_commands": 12,
            "speed_mps": 0.1,
            "settle_duration_s": 3.0,
            "settle_reset_count": 2,
        },
    }
    events = executor._events_for_action(event_action, event_result, executor.EventClock())
    terminal_events = [event for event in events if event["event"] == "terminal_settle_confirmed"]
    assert len(terminal_events) == 1
    assert terminal_events[0]["settle_duration_s"] == 3.0

    takeoff_backend = executor.RosBackend.__new__(executor.RosBackend)
    takeoff_backend._wait_for_takeoff_altitude = lambda _uav, _action: odom()
    takeoff_action = {
        "sequence": 1,
        "stage": "takeoff",
        "action": "publish_position_setpoint",
        "uav": "uav1",
        "goal": {"x": 0.0, "y": 0.0, "z": 1.0},
    }
    takeoff_verification = takeoff_backend.verify_action(
        takeoff_action,
        {"uavs": [{"uav_id": "uav1"}]},
    )
    assert takeoff_verification["event"] == "takeoff_altitude_confirmed"

    print("mission_executor_terminal_contract_check: PASS")


if __name__ == "__main__":
    main()
