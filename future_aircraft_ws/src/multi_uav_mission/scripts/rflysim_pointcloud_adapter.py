#!/usr/bin/env python3
"""ROS adapter from RflySim XYZ/seg clouds to faster_lio Ouster clouds."""

import json

from rflysim_cloud_contract import convert_cloud


class PointCloudAdapter:
    def __init__(self):
        import rospy
        from sensor_msgs.msg import PointCloud2
        from std_msgs.msg import String

        self.rospy = rospy
        self.PointCloud2 = PointCloud2
        self.String = String
        self.input_topic = rospy.get_param("~input_topic")
        self.output_topic = rospy.get_param("~output_topic")
        self.diagnostics_topic = rospy.get_param("~diagnostics_topic")
        self.frame_id = rospy.get_param("~frame_id")
        self.layout_width = int(rospy.get_param("~layout_width"))
        self.layout_height = int(rospy.get_param("~layout_height"))
        self.scan_period_sec = float(rospy.get_param("~scan_period_sec"))
        self.accepted_scans = 0
        self.output = rospy.Publisher(self.output_topic, PointCloud2, queue_size=2)
        self.diagnostics = rospy.Publisher(
            self.diagnostics_topic, String, queue_size=1, latch=True
        )
        self.subscription = rospy.Subscriber(
            self.input_topic, PointCloud2, self.handle_cloud, queue_size=2
        )

    def publish_diagnostics(self, status, source_stamp, **details):
        payload = {
            "accepted_scans": self.accepted_scans,
            "created_at": self.rospy.get_time(),
            "frame_id": self.frame_id,
            "input_topic": self.input_topic,
            "output_topic": self.output_topic,
            "source_stamp": source_stamp,
            "status": status,
        }
        payload.update(details)
        self.diagnostics.publish(self.String(data=json.dumps(payload, sort_keys=True)))

    def handle_cloud(self, message):
        from sensor_msgs.msg import PointField

        source_stamp = message.header.stamp.to_sec()
        fields = [
            {
                "name": field.name,
                "offset": field.offset,
                "datatype": field.datatype,
                "count": field.count,
            }
            for field in message.fields
        ]
        try:
            converted = convert_cloud(
                bytes(message.data),
                fields,
                message.width,
                message.height,
                message.point_step,
                self.layout_width,
                self.layout_height,
                self.scan_period_sec,
            )
        except ValueError as exc:
            self.publish_diagnostics("rejected", source_stamp, error=str(exc))
            self.rospy.logerr_throttle(2.0, "RflySim cloud rejected: %s", exc)
            return

        output = self.PointCloud2()
        output.header.seq = message.header.seq
        output.header.stamp = message.header.stamp
        output.header.frame_id = self.frame_id
        output.height = 1
        output.width = converted.accepted_points
        output.fields = [
            PointField(
                name=field.name,
                offset=field.offset,
                datatype=field.datatype,
                count=field.count,
            )
            for field in converted.fields
        ]
        output.is_bigendian = False
        output.point_step = converted.point_step
        output.row_step = converted.point_step * converted.accepted_points
        output.data = converted.data
        output.is_dense = True
        self.output.publish(output)
        self.accepted_scans += 1
        self.publish_diagnostics(
            "ready",
            source_stamp,
            accepted_points=converted.accepted_points,
            point_step=converted.point_step,
            time_span_sec=converted.time_span_sec,
        )


def main():
    import rospy

    rospy.init_node("rflysim_pointcloud_adapter", anonymous=False)
    PointCloudAdapter()
    rospy.spin()


if __name__ == "__main__":
    main()
