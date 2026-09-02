#!/usr/bin/env python3
"""RViz-only normalization for low-bandwidth per-UAV visualization data.

This node never publishes TF or control topics.  Marker and odometry numbers
are preserved; only visualization headers and a bounded path are produced.
"""

from __future__ import annotations

import copy
from collections import deque


def normalize_marker(message, frame_id):
    """Return a deep-copied Marker whose frame label is visualization-safe."""

    normalized = copy.deepcopy(message)
    normalized.header.frame_id = frame_id
    return normalized


def position_command_marker(message, frame_id, marker_factory=None):
    """Represent a PositionCommand position without changing its coordinates."""

    if marker_factory is None:
        from visualization_msgs.msg import Marker

        marker_factory = Marker
    marker = marker_factory()
    marker.header.stamp = copy.deepcopy(message.header.stamp)
    marker.header.frame_id = str(frame_id)
    marker.ns = "position_command"
    marker.id = 0
    marker.type = marker.SPHERE
    marker.action = marker.ADD
    marker.pose.position = copy.deepcopy(message.position)
    marker.pose.orientation.w = 1.0
    marker.scale.x = marker.scale.y = marker.scale.z = 0.15
    marker.color.r = 1.0
    marker.color.g = 0.65
    marker.color.b = 0.0
    marker.color.a = 1.0
    return marker


class BoundedPath:
    """Build a fixed-memory Path from odometry without changing pose values."""

    def __init__(self, frame_id, max_poses, path_factory=None, pose_factory=None):
        if int(max_poses) <= 0:
            raise ValueError("max_poses must be positive")
        if path_factory is None or pose_factory is None:
            from geometry_msgs.msg import PoseStamped
            from nav_msgs.msg import Path

            path_factory = path_factory or Path
            pose_factory = pose_factory or PoseStamped

        self._frame_id = str(frame_id)
        self._poses = deque(maxlen=int(max_poses))
        self._path = path_factory()
        self._pose_factory = pose_factory

    def append_odometry(self, odometry):
        pose = self._pose_factory()
        pose.header.stamp = copy.deepcopy(odometry.header.stamp)
        pose.header.frame_id = self._frame_id
        pose.pose = copy.deepcopy(odometry.pose.pose)
        self._poses.append(pose)

        self._path.header.stamp = copy.deepcopy(odometry.header.stamp)
        self._path.header.frame_id = self._frame_id
        self._path.poses = list(self._poses)
        return self._path


def main():
    import rospy
    from nav_msgs.msg import Odometry, Path
    from quadrotor_msgs.msg import PositionCommand
    from visualization_msgs.msg import Marker

    rospy.init_node("rviz_frame_adapter", anonymous=False)

    frame_id = rospy.get_param("~frame_id")
    odom_topic = rospy.get_param("~odom_topic")
    path_topic = rospy.get_param("~path_topic", "viz/path")
    optimal_marker_topic = rospy.get_param("~optimal_marker_topic")
    optimal_marker_output_topic = rospy.get_param(
        "~optimal_marker_output_topic", "viz/optimal_trajectory"
    )
    goal_marker_topic = rospy.get_param("~goal_marker_topic")
    goal_marker_output_topic = rospy.get_param("~goal_marker_output_topic", "viz/goal")
    position_command_topic = rospy.get_param("~position_command_topic")
    position_command_output_topic = rospy.get_param(
        "~position_command_output_topic", "viz/position_command"
    )
    max_path_poses = int(rospy.get_param("~max_path_poses", 600))

    path_builder = BoundedPath(frame_id, max_path_poses)
    path_publisher = rospy.Publisher(path_topic, Path, queue_size=2)
    optimal_publisher = rospy.Publisher(
        optimal_marker_output_topic, Marker, queue_size=2
    )
    goal_publisher = rospy.Publisher(goal_marker_output_topic, Marker, queue_size=2)
    position_command_publisher = rospy.Publisher(
        position_command_output_topic, Marker, queue_size=2
    )

    def odometry_callback(message):
        path_publisher.publish(path_builder.append_odometry(message))

    def optimal_callback(message):
        optimal_publisher.publish(normalize_marker(message, frame_id))

    def goal_callback(message):
        goal_publisher.publish(normalize_marker(message, frame_id))

    def position_command_callback(message):
        position_command_publisher.publish(position_command_marker(message, frame_id))

    rospy.Subscriber(odom_topic, Odometry, odometry_callback, queue_size=10)
    rospy.Subscriber(optimal_marker_topic, Marker, optimal_callback, queue_size=2)
    rospy.Subscriber(goal_marker_topic, Marker, goal_callback, queue_size=2)
    rospy.Subscriber(
        position_command_topic, PositionCommand, position_command_callback, queue_size=2
    )
    rospy.loginfo(
        "RViz adapter ready frame=%s odom=%s path=%s",
        frame_id,
        odom_topic,
        path_topic,
    )
    rospy.spin()


if __name__ == "__main__":
    main()
