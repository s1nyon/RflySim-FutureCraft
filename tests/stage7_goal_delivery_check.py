#!/usr/bin/env python3
"""Behavior checks for reliable, namespaced Stage 7 planner goals."""

from __future__ import annotations

import argparse
import importlib.util
import sys
import xml.etree.ElementTree as ET
from pathlib import Path
from types import SimpleNamespace


def load_executor(module_path):
    sys.path.insert(0, str(module_path.parent))
    spec = importlib.util.spec_from_file_location("mission_executor", str(module_path))
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


class DummyPoseStamped:
    def __init__(self):
        self.header = SimpleNamespace(stamp=None, frame_id="")
        self.pose = SimpleNamespace(
            position=SimpleNamespace(x=0.0, y=0.0, z=0.0),
            orientation=SimpleNamespace(w=0.0),
        )


class FakePublisher:
    def __init__(self):
        self.connection_checks = 0
        self.messages = []

    def get_num_connections(self):
        self.connection_checks += 1
        return 1

    def publish(self, message):
        self.messages.append(message)


class FakeRospy:
    def __init__(self):
        self.publishers = []
        self.Time = SimpleNamespace(now=lambda: "stamp")

    def Publisher(self, *_args, **_kwargs):
        publisher = FakePublisher()
        self.publishers.append(publisher)
        return publisher

    def Rate(self, _rate):
        return SimpleNamespace(sleep=lambda: None)

    def is_shutdown(self):
        return False


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--single-launch", required=True, type=Path)
    parser.add_argument("--dual-launch", required=True, type=Path)
    parser.add_argument("--executor-module", required=True, type=Path)
    args = parser.parse_args()

    single_root = ET.parse(args.single_launch).getroot()
    goal_arg = single_root.find("./arg[@name='goal_topic']")
    planner_node = single_root.find("./node[@pkg='ego_planner'][@type='ego_planner_node']")
    direct_goal_remap = planner_node.find("./remap[@from='/move_base_simple/goal']")
    assert goal_arg is not None
    assert direct_goal_remap is not None
    assert direct_goal_remap.attrib["to"] == "$(arg goal_topic)"

    dual_root = ET.parse(args.dual_launch).getroot()
    include_goal_values = [
        arg.attrib["value"]
        for arg in dual_root.findall("./include/arg[@name='goal_topic']")
    ]
    assert include_goal_values == ["$(arg uav1_goal_topic)", "$(arg uav2_goal_topic)"]

    executor = load_executor(args.executor_module)
    backend = executor.RosBackend.__new__(executor.RosBackend)
    backend.rospy = FakeRospy()
    backend.PoseStamped = DummyPoseStamped
    goals = [
        {"x": 1.0, "y": 2.0, "z": 1.0},
        {"x": 3.0, "y": 4.0, "z": 1.0},
    ]
    for goal in goals:
        result = backend._publish_planner_goal(
            {
                "topic": "/uav1/planning/goal",
                "goal": goal,
                "timeout_s": 0.1,
            }
        )
        assert result["status"] == "ros_success"

    assert len(backend.rospy.publishers) == 1
    published = backend.rospy.publishers[0].messages
    assert len(published) == 2
    for message, goal in zip(published, goals):
        assert message.pose.position.x == goal["x"]
        assert message.pose.position.y == goal["y"]
        assert message.pose.position.z == goal["z"]
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
