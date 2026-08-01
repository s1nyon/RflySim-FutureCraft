#!/usr/bin/env python3
"""Relay nav_msgs/Odometry while rewriting frame ids for namespaced MAVROS."""

from __future__ import annotations

import argparse
import copy
import sys


def rewrite_odometry_frames(message, frame_id, child_frame_id):
    rewritten = copy.deepcopy(message)
    rewritten.header.frame_id = frame_id
    rewritten.child_frame_id = child_frame_id
    return rewritten


def run_ros_node(input_topic, output_topic, frame_id, child_frame_id, queue_size):
    import rospy
    from nav_msgs.msg import Odometry

    publisher = rospy.Publisher(output_topic, Odometry, queue_size=queue_size)

    def callback(message):
        publisher.publish(rewrite_odometry_frames(message, frame_id, child_frame_id))

    rospy.Subscriber(input_topic, Odometry, callback, queue_size=queue_size)
    rospy.loginfo(
        "odom_frame_relay: %s -> %s (%s, %s)",
        input_topic,
        output_topic,
        frame_id,
        child_frame_id,
    )
    rospy.spin()


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--input-topic")
    parser.add_argument("--output-topic")
    parser.add_argument("--frame-id")
    parser.add_argument("--child-frame-id")
    parser.add_argument("--queue-size", type=int, default=20)
    args, _unknown = parser.parse_known_args(argv)

    import rospy

    rospy.init_node("odom_frame_relay", anonymous=False)
    input_topic = args.input_topic or rospy.get_param("~input_topic")
    output_topic = args.output_topic or rospy.get_param("~output_topic")
    frame_id = args.frame_id or rospy.get_param("~frame_id")
    child_frame_id = args.child_frame_id or rospy.get_param("~child_frame_id")
    queue_size = int(rospy.get_param("~queue_size", args.queue_size))
    run_ros_node(input_topic, output_topic, frame_id, child_frame_id, queue_size)
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
