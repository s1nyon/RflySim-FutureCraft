#!/usr/bin/env python3
"""Regression check: ROS backend must fail fast when ROS master is unavailable."""

import argparse
import importlib.util
import sys
from pathlib import Path


class FakeMaster:
    def getPid(self):
        raise RuntimeError("master unavailable")


class FakeCore:
    @staticmethod
    def is_initialized():
        return False


class FakeRospy:
    core = FakeCore()
    AnyMsg = object

    @staticmethod
    def init_node(*args, **kwargs):
        return None

    @staticmethod
    def get_master():
        return FakeMaster()


class FakeModule:
    pass


def install_fake_ros_modules():
    sys.modules["rospy"] = FakeRospy
    geometry_msgs = FakeModule()
    geometry_msgs_msg = FakeModule()
    geometry_msgs_msg.PoseStamped = object
    sys.modules["geometry_msgs"] = geometry_msgs
    sys.modules["geometry_msgs.msg"] = geometry_msgs_msg

    mavros_msgs = FakeModule()
    mavros_msgs_msg = FakeModule()
    mavros_msgs_msg.PositionTarget = object
    mavros_msgs_srv = FakeModule()
    mavros_msgs_srv.CommandBool = object
    mavros_msgs_srv.SetMode = object
    sys.modules["mavros_msgs"] = mavros_msgs
    sys.modules["mavros_msgs.msg"] = mavros_msgs_msg
    sys.modules["mavros_msgs.srv"] = mavros_msgs_srv

    std_srvs = FakeModule()
    std_srvs_srv = FakeModule()
    std_srvs_srv.Trigger = object
    sys.modules["std_srvs"] = std_srvs
    sys.modules["std_srvs.srv"] = std_srvs_srv


def load_module(script_path):
    spec = importlib.util.spec_from_file_location("mavros_smoke_check", script_path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--script", required=True, type=Path)
    args = parser.parse_args()

    install_fake_ros_modules()
    module = load_module(args.script)
    try:
        module.RosChecker(timeout_s=0.1)
    except RuntimeError as exc:
        message = str(exc)
        if "ROS master" not in message:
            print(f"[ERROR] wrong failure message: {message}", file=sys.stderr)
            return 1
        return 0
    print("[ERROR] RosChecker did not fail when ROS master was unavailable", file=sys.stderr)
    return 1


if __name__ == "__main__":
    raise SystemExit(main())
