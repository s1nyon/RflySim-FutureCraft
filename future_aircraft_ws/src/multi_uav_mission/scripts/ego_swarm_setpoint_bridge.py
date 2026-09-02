#!/usr/bin/env python3
"""Continuously bridge ego-swarm PositionCommand messages to MAVROS setpoints."""

from __future__ import annotations

import argparse
import math
from pathlib import Path
from types import SimpleNamespace

try:
    from course_geofence import Geofence, GeofenceViolation, validate_point
except ModuleNotFoundError:
    import sys
    sys.path.insert(0, str(Path(__file__).resolve().parent))
    from course_geofence import Geofence, GeofenceViolation, validate_point


def position_command_to_target(command, position_target_type, fence=None):
    if fence is not None:
        validate_point((command.position.x, command.position.y, command.position.z), fence)
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


def goal_matches_expected(message, expected):
    position = message.pose.position
    return (
        str(message.header.frame_id) == str(expected.frame_id)
        and math.dist(
            (float(position.x), float(position.y), float(position.z)),
            (float(expected.x), float(expected.y), float(expected.z)),
        ) <= float(expected.tolerance_m)
    )


def target_for_publication(state, wait_for_first_planner_command):
    """Return the active target, or no target before the opt-in EGO handoff.

    The gated mode lets a direct takeoff publisher remain the only MAVROS
    setpoint source until EGO has produced its first command.
    """
    if wait_for_first_planner_command and not (
        state["matching_goal_received"] and state["planner_command_received"]
    ):
        return None
    return state["target"]


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--planner-topic", required=True)
    parser.add_argument("--setpoint-topic", required=True)
    parser.add_argument("--initial-x", required=True, type=float)
    parser.add_argument("--initial-y", required=True, type=float)
    parser.add_argument("--initial-z", required=True, type=float)
    parser.add_argument("--yaw", type=float, default=0.0)
    parser.add_argument("--rate-hz", type=float, default=20.0)
    parser.add_argument("--wait-for-matching-planner-goal", action="store_true")
    parser.add_argument("--goal-topic")
    parser.add_argument("--expected-goal-frame")
    parser.add_argument("--expected-goal-x", type=float)
    parser.add_argument("--expected-goal-y", type=float)
    parser.add_argument("--expected-goal-z", type=float)
    parser.add_argument("--expected-goal-tolerance-m", type=float, default=1e-3)
    parser.add_argument("--min-x", type=float, default=-1.0)
    parser.add_argument("--max-x", type=float, default=17.0)
    parser.add_argument("--min-y", type=float, default=-2.0)
    parser.add_argument("--max-y", type=float, default=7.0)
    parser.add_argument("--min-z", type=float, default=-0.5)
    parser.add_argument("--max-z", type=float, default=2.0)
    args = parser.parse_args(argv)
    if args.rate_hz < 20.0:
        parser.error("--rate-hz must be at least 20")
    expected_fields = (
        args.goal_topic, args.expected_goal_frame, args.expected_goal_x,
        args.expected_goal_y, args.expected_goal_z,
    )
    if args.wait_for_matching_planner_goal and any(value is None for value in expected_fields):
        parser.error("matching-goal handoff requires goal topic, frame, and XYZ")
    if args.expected_goal_tolerance_m < 0:
        parser.error("--expected-goal-tolerance-m must be non-negative")

    import rospy
    from mavros_msgs.msg import PositionTarget
    from geometry_msgs.msg import PoseStamped
    from quadrotor_msgs.msg import PositionCommand

    rospy.init_node("future_aircraft_ego_swarm_setpoint_bridge", anonymous=True)
    fence = Geofence(args.min_x, args.max_x, args.min_y, args.max_y, args.min_z, args.max_z)
    publisher = rospy.Publisher(args.setpoint_topic, PositionTarget, queue_size=10)
    state = {
        "target": initial_target(
            PositionTarget,
            args.initial_x,
            args.initial_y,
            args.initial_z,
            args.yaw,
        ),
        "matching_goal_received": not args.wait_for_matching_planner_goal,
        "planner_command_received": False,
    }
    expected_goal = SimpleNamespace(
        frame_id=args.expected_goal_frame,
        x=args.expected_goal_x,
        y=args.expected_goal_y,
        z=args.expected_goal_z,
        tolerance_m=args.expected_goal_tolerance_m,
    )

    def goal_callback(message):
        if goal_matches_expected(message, expected_goal):
            state["matching_goal_received"] = True
            state["planner_command_received"] = False

    def planner_callback(command):
        if not state["matching_goal_received"]:
            return
        try:
            state["target"] = position_command_to_target(command, PositionTarget, fence)
            state["planner_command_received"] = True
        except GeofenceViolation as exc:
            rospy.logerr_throttle(1.0, "planner command rejected by course geofence: %s", exc)

    rospy.Subscriber(args.planner_topic, PositionCommand, planner_callback, queue_size=10)
    if args.wait_for_matching_planner_goal:
        rospy.Subscriber(args.goal_topic, PoseStamped, goal_callback, queue_size=10)
    rate = rospy.Rate(args.rate_hz)
    while not rospy.is_shutdown():
        target = target_for_publication(state, args.wait_for_matching_planner_goal)
        if target is not None:
            target.header.stamp = rospy.Time.now()
            publisher.publish(target)
        rate.sleep()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
