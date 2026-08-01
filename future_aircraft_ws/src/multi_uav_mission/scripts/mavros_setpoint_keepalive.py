#!/usr/bin/env python3
"""Continuously publish MAVROS raw local position setpoints."""

from __future__ import annotations

import argparse
import signal
import sys


def build_position_target(PositionTarget, goal):
    message = PositionTarget()
    message.coordinate_frame = PositionTarget.FRAME_LOCAL_NED
    message.type_mask = (
        PositionTarget.IGNORE_VX
        | PositionTarget.IGNORE_VY
        | PositionTarget.IGNORE_VZ
        | PositionTarget.IGNORE_AFX
        | PositionTarget.IGNORE_AFY
        | PositionTarget.IGNORE_AFZ
        | PositionTarget.IGNORE_YAW_RATE
        | PositionTarget.FORCE
    )
    message.position.x = float(goal["x"])
    message.position.y = float(goal["y"])
    message.position.z = float(goal["z"])
    message.yaw = float(goal.get("yaw", 0.0))
    return message


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--topic", required=True)
    parser.add_argument("--x", required=True, type=float)
    parser.add_argument("--y", required=True, type=float)
    parser.add_argument("--z", required=True, type=float)
    parser.add_argument("--yaw", type=float, default=0.0)
    parser.add_argument("--rate-hz", type=float, default=20.0)
    args = parser.parse_args(argv)

    import rospy
    from mavros_msgs.msg import PositionTarget

    rospy.init_node("future_aircraft_setpoint_keepalive", anonymous=True)
    publisher = rospy.Publisher(args.topic, PositionTarget, queue_size=10)
    message = build_position_target(
        PositionTarget,
        {"x": args.x, "y": args.y, "z": args.z, "yaw": args.yaw},
    )

    stop = False

    def _stop(_signum, _frame):
        nonlocal stop
        stop = True

    signal.signal(signal.SIGINT, _stop)
    signal.signal(signal.SIGTERM, _stop)
    rate = rospy.Rate(args.rate_hz)
    while not stop and not rospy.is_shutdown():
        message.header.stamp = rospy.Time.now()
        publisher.publish(message)
        rate.sleep()
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
