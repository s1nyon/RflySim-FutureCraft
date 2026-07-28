#!/usr/bin/env python3
"""Offline fake-ROS check for the Stage 6B sim-vision target bridge."""

import argparse
import json
import sys
from pathlib import Path


def main(argv=None):
    parser = argparse.ArgumentParser(description="Check mission_executor ROS sim-vision bridge without ROS")
    parser.add_argument("--scripts-dir", required=True, type=Path)
    parser.add_argument("--plan", required=True, type=Path)
    parser.add_argument("--target-results", required=True, type=Path)
    args = parser.parse_args(argv)

    sys.path.insert(0, str(args.scripts_dir))
    import mission_executor

    plan = json.loads(args.plan.read_text(encoding="utf-8"))
    target_payload = args.target_results.read_text(encoding="utf-8")
    action = next(item for item in plan["actions"] if item["stage"] == "collaborative_target_work")

    class Response:
        success = True
        message = target_payload

    class FakeRospy:
        def __init__(self):
            self.wait_timeout = None

        def wait_for_service(self, _service, timeout):
            self.wait_timeout = timeout

        def ServiceProxy(self, _service, _service_type):
            return lambda: Response()

    fake_rospy = FakeRospy()
    backend = mission_executor.RosBackend.__new__(mission_executor.RosBackend)
    backend.rospy = fake_rospy
    backend.Trigger = object

    result = mission_executor.RosBackend._call_service(backend, action)
    expected_timeout = float(action["request"]["timeout_s"])
    if fake_rospy.wait_timeout != expected_timeout:
        raise AssertionError(f"target provider wait timeout={fake_rospy.wait_timeout}, expected={expected_timeout}")
    if result["status"] != "ros_target_results_received":
        raise AssertionError(f"unexpected ROS target result status: {result['status']}")
    if result["target_results"]["source_mode"] != "sim_vision":
        raise AssertionError("ROS target provider payload did not preserve sim_vision source_mode")
    if len(result["target_results"]["targets"]) != 3:
        raise AssertionError("ROS target provider payload did not return three targets")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
