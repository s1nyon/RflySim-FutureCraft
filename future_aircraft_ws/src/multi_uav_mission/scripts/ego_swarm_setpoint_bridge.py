#!/usr/bin/env python3
"""Continuously bridge ego-swarm PositionCommand messages to MAVROS setpoints."""

from __future__ import annotations

import argparse


def position_command_to_target(command, position_target_type):
    target = position_target_type()
    target.coordinate_frame = position_target_type.FRAME_LOCAL_NED
    target.type_mask = (
        position_target_type.IGNORE_VX
        | position_target_type.IGNORE_VY
        | position_target_type.IGNORE_VZ
        | position_target_type.IGNORE_AFX
        | position_target_type.IGNORE_AFY
        | position_target_type.IGNORE_AFZ
        | position_target_type.FORCE
        | position_target_type.IGNORE_YAW_RATE
    )
    target.position.x = float(command.position.x)
    target.position.y = float(command.position.y)
    target.position.z = float(command.position.z)
    target.yaw = float(command.yaw)
    return target


def initial_target(position_target_type, x, y, z, yaw):
    class InitialCommand:
        pass

    command = InitialCommand()
    command.position = InitialCommand()
    command.position.x = x
    command.position.y = y
    command.position.z = z
    command.yaw = yaw
    return position_command_to_target(command, position_target_type)


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--planner-topic", required=True)
    parser.add_argument("--setpoint-topic", required=True)
    parser.add_argument("--initial-x", required=True, type=float)
    parser.add_argument("--initial-y", required=True, type=float)
    parser.add_argument("--initial-z", required=True, type=float)
    parser.add_argument("--yaw", type=float, default=0.0)
    parser.add_argument("--rate-hz", type=float, default=20.0)
    args = parser.parse_args(argv)
    if args.rate_hz < 20.0:
        parser.error("--rate-hz must be at least 20")

    import rospy
    from mavros_msgs.msg import PositionTarget
    from quadrotor_msgs.msg import PositionCommand

    rospy.init_node("future_aircraft_ego_swarm_setpoint_bridge", anonymous=True)
    publisher = rospy.Publisher(args.setpoint_topic, PositionTarget, queue_size=10)
    state = {
        "target": initial_target(
            PositionTarget,
            args.initial_x,
            args.initial_y,
            args.initial_z,
            args.yaw,
        )
    }

    def planner_callback(command):
        state["target"] = position_command_to_target(command, PositionTarget)

    rospy.Subscriber(args.planner_topic, PositionCommand, planner_callback, queue_size=10)
    rate = rospy.Rate(args.rate_hz)
    while not rospy.is_shutdown():
        state["target"].header.stamp = rospy.Time.now()
        publisher.publish(state["target"])
        rate.sleep()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
