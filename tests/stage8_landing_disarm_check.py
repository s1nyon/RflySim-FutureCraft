#!/usr/bin/env python3
"""Regression guard: AUTO.LAND completes on disarm even if the sim hovers
just above the altitude threshold.

Live stability runs repeatedly timed out waiting for z<=0.25m while PX4 had
already disarmed (armed=False) and hovered at ~0.29-0.55m.  The executor must
accept a disarmed vehicle at low altitude as landed.
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


class FakeRospy:
    def __init__(self, armed, odom_z):
        self.armed = armed
        self.odom_z = odom_z
        self.calls = []

    def wait_for_message(self, topic, _topic_type, timeout=0.5):
        self.calls.append((topic, timeout))
        if topic.endswith("/state"):
            return SimpleNamespace(armed=self.armed)
        return SimpleNamespace(
            pose=SimpleNamespace(
                pose=SimpleNamespace(
                    position=SimpleNamespace(x=15.9, y=5.2, z=self.odom_z),
                )
            )
        )

    def is_shutdown(self):
        return False


class DummyOdometry:
    pass


class DummyState:
    pass


def landing_action(timeout_s=0.5):
    return {
        "timeout_s": timeout_s,
        "fallback_goal": {"z": 0.0},
    }


def uav_config():
    return {
        "uav_id": "uav2",
        "state_topic": "/uav2/mavros/state",
        "odom_topic": "/uav2/mavros/local_position/odom",
    }


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--executor-module", required=True, type=Path)
    args = parser.parse_args()

    executor = load_executor(args.executor_module)
    backend = executor.RosBackend.__new__(executor.RosBackend)
    backend.rospy = FakeRospy(armed=False, odom_z=0.35)
    backend.State = DummyState
    backend.Odometry = DummyOdometry
    result = backend._wait_for_landing(uav_config(), landing_action(timeout_s=2.0))
    assert result is not None

    backend2 = executor.RosBackend.__new__(executor.RosBackend)
    backend2.rospy = FakeRospy(armed=True, odom_z=0.35)
    backend2.State = DummyState
    backend2.Odometry = DummyOdometry
    raised = False
    try:
        backend2._wait_for_landing(uav_config(), landing_action(timeout_s=0.5))
    except RuntimeError:
        raised = True
    assert raised, "armed vehicle above threshold must not be treated as landed"

    backend3 = executor.RosBackend.__new__(executor.RosBackend)
    backend3.rospy = FakeRospy(armed=False, odom_z=1.5)
    backend3.State = DummyState
    backend3.Odometry = DummyOdometry
    raised3 = False
    try:
        backend3._wait_for_landing(uav_config(), landing_action(timeout_s=0.5))
    except RuntimeError:
        raised3 = True
    assert raised3, "disarm at cruise altitude must not be treated as landing"

    print("stage8 landing disarm: PASS")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
