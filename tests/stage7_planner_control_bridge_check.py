#!/usr/bin/env python3
"""Behavior checks for the Stage 7 planner-command control bridge."""

from __future__ import annotations

import argparse
import importlib.util
import json
import sys
import threading
import time
from pathlib import Path
from types import SimpleNamespace


def load_module(name, path):
    spec = importlib.util.spec_from_file_location(name, str(path))
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


class DummyPositionTarget:
    FRAME_LOCAL_NED = 1
    IGNORE_VX = 8
    IGNORE_VY = 16
    IGNORE_VZ = 32
    IGNORE_AFX = 64
    IGNORE_AFY = 128
    IGNORE_AFZ = 256
    FORCE = 512
    IGNORE_YAW_RATE = 2048

    def __init__(self):
        self.coordinate_frame = 0
        self.type_mask = 0
        self.position = SimpleNamespace(x=0.0, y=0.0, z=0.0)
        self.yaw = 0.0


class AlreadyAtGoalRospy:
    """Simulate MAVROS/EGO publishers with persistent subscribers.

    The executor now subscribes once per topic and caches the latest message
    instead of calling ``wait_for_message`` per navigation goal.  The odom
    subscriber immediately delivers a position equal to the goal so the
    already-reached path must succeed without ever waiting for a planner
    command.
    """

    def __init__(self):
        self.odom = SimpleNamespace(
            pose=SimpleNamespace(
                pose=SimpleNamespace(
                    position=SimpleNamespace(x=0.7, y=1.5, z=1.0)
                )
            )
        )
        self.subscribers = []
        self.planner_wait_attempted = False
        self._stop = threading.Event()
        self._publisher = threading.Thread(target=self._stream_odom, daemon=True)
        self._publisher.start()

    def _stream_odom(self):
        while not self._stop.is_set():
            for subscriber in list(self.subscribers):
                if subscriber.topic.endswith("/mavros/odometry/in"):
                    subscriber.callback(self.odom)
            time.sleep(0.02)

    def close(self):
        self._stop.set()
        self._publisher.join(timeout=1.0)

    def Subscriber(self, topic, _message_type, callback, queue_size=1):
        subscriber = SimpleNamespace(topic=topic, queue_size=queue_size, callback=callback)
        self.subscribers.append(subscriber)
        return subscriber

    @staticmethod
    def is_shutdown():
        return False


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--bridge-module", required=True, type=Path)
    parser.add_argument("--plan-module", required=True, type=Path)
    parser.add_argument("--config", required=True, type=Path)
    parser.add_argument("--executor-module", required=True, type=Path)
    args = parser.parse_args()

    bridge = load_module("ego_swarm_setpoint_bridge", args.bridge_module)
    command = SimpleNamespace(
        position=SimpleNamespace(x=1.25, y=-0.5, z=1.1),
        yaw=0.75,
    )
    target = bridge.position_command_to_target(command, DummyPositionTarget)
    assert target.coordinate_frame == DummyPositionTarget.FRAME_LOCAL_NED
    assert (target.position.x, target.position.y, target.position.z) == (1.25, -0.5, 1.1)
    assert target.yaw == 0.75
    assert target.type_mask & DummyPositionTarget.IGNORE_VX
    assert target.type_mask & DummyPositionTarget.IGNORE_AFX
    assert target.type_mask & DummyPositionTarget.IGNORE_YAW_RATE

    plan_module = load_module("stage7_flight_plan", args.plan_module)
    plan = plan_module.build_plan(json.loads(args.config.read_text(encoding="utf-8")))
    navigation_actions = [
        action for action in plan["actions"] if action["stage"] == "collaborative_navigate"
    ]
    assert [action["action"] for action in navigation_actions] == [
        "publish_planner_goal",
        "publish_planner_goal",
        "verify_planned_navigation",
        "verify_planned_navigation",
    ]
    assert [action["goal"]["x"] for action in navigation_actions[:2]] == [0.7, 1.7]
    for action in navigation_actions[2:]:
        assert action["planner_cmd_topic"].startswith(f"/{action['uav']}/planning/")
        assert action["mavros_odom_topic"].startswith(f"/{action['uav']}/mavros/")
        assert action["tolerance_m"] == 0.3

    sys.path.insert(0, str(args.executor_module.parent))
    executor = load_module("mission_executor_stage7", args.executor_module)
    executor.validate_plan(plan)
    backend = executor.RosBackend.__new__(executor.RosBackend)
    backend.rospy = AlreadyAtGoalRospy()
    backend.PositionCommand = object
    backend.Odometry = object
    reached = backend._verify_planned_navigation(
        {
            "uav": "uav1",
            "planner_cmd_topic": "/uav1/planning/pos_cmd",
            "mavros_odom_topic": "/uav1/mavros/odometry/in",
            "goal": {"x": 0.7, "y": 1.5, "z": 1.0},
            "timeout_s": 1.0,
            "tolerance_m": 0.3,
        }
    )
    assert reached["status"] == "ros_navigation_success"
    assert reached["navigation"]["planner_commands"] == 0
    planner_subscribers = [
        subscriber
        for subscriber in backend.rospy.subscribers
        if subscriber.topic.endswith("/planning/pos_cmd")
    ]
    assert len(planner_subscribers) == 1, "navigation must create one persistent planner subscriber"
    backend.rospy.close()
    events = executor._events_for_action(
        navigation_actions[2],
        {
            "status": "ros_navigation_success",
            "detail": "goal reached",
            "navigation": {"distance_m": 0.12, "planner_commands": 42},
        },
        executor.EventClock(),
    )
    assert any(event["event"] == "navigation_confirmed" for event in events)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
