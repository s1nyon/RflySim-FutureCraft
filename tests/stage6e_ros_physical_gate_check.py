#!/usr/bin/env python3
"""Offline checks that Stage 6E ROS execution gates on real PX4 state."""

import argparse
import sys
from pathlib import Path


def _load_executor(scripts_dir):
    sys.path.insert(0, str(scripts_dir))
    import mission_executor

    return mission_executor


def _minimal_live_config():
    return {
        "simulation_arm_policy": {
            "allow_arm": True,
            "mode": "simulation_only",
            "operator_ack": "simulation_stage5e",
        },
        "uavs": [
            {
                "uav_id": "uav1",
                "namespace": "/uav1",
                "state_topic": "/uav1/mavros/state",
                "odom_topic": "/uav1/mavros/odometry/in",
            }
        ],
    }


def check_rejects_failed_set_mode_response(mission_executor):
    class Response:
        mode_sent = False

    class FakeRospy:
        def wait_for_service(self, _service, timeout):
            self.timeout = timeout

        def ServiceProxy(self, _service, _service_type):
            return lambda custom_mode: Response()

    backend = mission_executor.RosBackend.__new__(mission_executor.RosBackend)
    backend.rospy = FakeRospy()
    backend.SetMode = object

    action = {
        "action": "call_service",
        "request": {"custom_mode": "OFFBOARD"},
        "service": "/uav1/mavros/set_mode",
        "stage": "multi_takeoff",
        "timeout_s": 1,
        "uav": "uav1",
    }
    try:
        mission_executor.RosBackend._call_service(backend, action)
    except RuntimeError as exc:
        if "set_mode failed" not in str(exc):
            raise AssertionError(f"wrong set_mode failure: {exc}") from exc
        return
    raise AssertionError("set_mode response mode_sent=False must fail the executor")


def check_rejects_failed_arming_response(mission_executor):
    class Response:
        success = False
        result = 4

    class FakeRospy:
        def wait_for_service(self, _service, timeout):
            self.timeout = timeout

        def ServiceProxy(self, _service, _service_type):
            return lambda value: Response()

    backend = mission_executor.RosBackend.__new__(mission_executor.RosBackend)
    backend.rospy = FakeRospy()
    backend.CommandBool = object

    action = {
        "action": "call_service",
        "request": {"value": True},
        "service": "/uav1/mavros/cmd/arming",
        "stage": "multi_takeoff",
        "timeout_s": 1,
        "uav": "uav1",
    }
    try:
        mission_executor.RosBackend._call_service(backend, action)
    except RuntimeError as exc:
        if "arming failed" not in str(exc):
            raise AssertionError(f"wrong arming failure: {exc}") from exc
        return
    raise AssertionError("arming response success=False must fail the executor")


def check_ros_takeoff_requires_physical_verification(mission_executor):
    class FakeRosBackend:
        name = "ros"

        def execute(self, action):
            return {"status": "ros_success", "detail": f"executed {action['action']}"}

        def verify_action(self, action, live_config):
            if action["stage"] == "multi_takeoff" and action["action"] == "publish_position_setpoint":
                raise RuntimeError("simulated no climb")
            return None

    plan = {
        "mission_name": "stage6e_physical_gate_check",
        "actions": [
            {
                "action": "publish_position_setpoint",
                "goal": {"x": 0.0, "y": 0.0, "z": 1.2},
                "rate_hz": 20,
                "sequence": 1,
                "stage": "multi_takeoff",
                "timeout_s": 1,
                "topic": "/uav1/mavros/setpoint_raw/local",
                "uav": "uav1",
            }
        ],
    }
    try:
        mission_executor.execute_plan(
            plan,
            FakeRosBackend(),
            allow_arm=True,
            simulation_only=True,
            live_config=_minimal_live_config(),
        )
    except RuntimeError as exc:
        if "simulated no climb" not in str(exc):
            raise AssertionError(f"wrong physical verification failure: {exc}") from exc
        return
    raise AssertionError("ROS takeoff setpoint must be followed by physical climb verification")


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--scripts-dir", required=True, type=Path)
    args = parser.parse_args(argv)

    mission_executor = _load_executor(args.scripts_dir)
    check_rejects_failed_set_mode_response(mission_executor)
    check_rejects_failed_arming_response(mission_executor)
    check_ros_takeoff_requires_physical_verification(mission_executor)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
