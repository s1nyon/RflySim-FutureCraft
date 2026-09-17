#include "future_aircraft_mission/shared_frame_adapter.hpp"

#include <sensor_msgs/point_cloud2_iterator.h>

#include <cmath>
#include <stdexcept>

namespace
{

constexpr double kPi =
    3.14159265358979323846;

double degreesToRadians(double degrees)
{
    return degrees * kPi / 180.0;
}

}  // namespace


SharedFrameAdapter::SharedFrameAdapter(
    ros::NodeHandle& nh,
    ros::NodeHandle& pnh)
    : _nh(nh),
      _pnh(pnh)
{
    _pnh.param<std::string>(
        "local_odom_topic",
        _local_odom_topic,
        "mavros/odometry/out"
    );

    _pnh.param<std::string>(
        "local_cloud_topic",
        _local_cloud_topic,
        "slam/cloud_registered"
    );

    _pnh.param<std::string>(
        "local_goal_topic",
        _local_goal_topic,
        "planning/goal_local"
    );

    _pnh.param<std::string>(
        "world_odom_topic",
        _world_odom_topic,
        "planning/odom_world"
    );

    _pnh.param<std::string>(
        "world_cloud_topic",
        _world_cloud_topic,
        "planning/cloud_world"
    );

    _pnh.param<std::string>(
        "world_goal_topic",
        _world_goal_topic,
        "planning/goal"
    );

    _pnh.param<std::string>(
        "world_frame",
        _world_frame,
        "world"
    );

    double origin_x = 0.0;
    double origin_y = 0.0;
    double origin_z = 0.0;
    double origin_yaw_deg = 0.0;

    _pnh.param<double>(
        "origin_x",
        origin_x,
        0.0
    );

    _pnh.param<double>(
        "origin_y",
        origin_y,
        0.0
    );

    _pnh.param<double>(
        "origin_z",
        origin_z,
        0.0
    );

    _pnh.param<double>(
        "origin_yaw_deg",
        origin_yaw_deg,
        0.0
    );

    _transform = PlanarFrameTransform(
        true,
        origin_x,
        origin_y,
        origin_z,
        degreesToRadians(origin_yaw_deg)
    );

    _world_odom_pub =
        _nh.advertise<nav_msgs::Odometry>(
            _world_odom_topic,
            10
        );

    _world_cloud_pub =
        _nh.advertise<sensor_msgs::PointCloud2>(
            _world_cloud_topic,
            2
        );

    _world_goal_pub =
        _nh.advertise<geometry_msgs::PoseStamped>(
            _world_goal_topic,
            10,
            true
        );

    _local_odom_sub =
        _nh.subscribe(
            _local_odom_topic,
            10,
            &SharedFrameAdapter::odomCallback,
            this
        );

    _local_cloud_sub =
        _nh.subscribe(
            _local_cloud_topic,
            2,
            &SharedFrameAdapter::cloudCallback,
            this
        );

    _local_goal_sub =
        _nh.subscribe(
            _local_goal_topic,
            10,
            &SharedFrameAdapter::goalCallback,
            this
        );

    ROS_INFO(
        "SharedFrameAdapter ready: "
        "origin=(%.3f, %.3f, %.3f), yaw=%.2f deg",
        origin_x,
        origin_y,
        origin_z,
        origin_yaw_deg
    );
}


void SharedFrameAdapter::odomCallback(
    const nav_msgs::Odometry::ConstPtr& msg)
{
    nav_msgs::Odometry output = *msg;

    output.header.frame_id =
        _world_frame;

    output.pose.pose.position =
        _transform.localToWorld(
            msg->pose.pose.position
        );

    output.pose.pose.orientation =
        _transform.localToWorldOrientation(
            msg->pose.pose.orientation
        );

    /*
     * EGO uses the numeric velocity as its planning-state
     * velocity, so express the vector in the same shared
     * world axes as the transformed position.
     *
     * Current Competition Course V2 uses spawn yaw = 0 deg,
     * so this is identical to the current values there.
     */
    output.twist.twist.linear =
        _transform.localToWorldVector(
            msg->twist.twist.linear
        );

    output.twist.twist.angular =
        _transform.localToWorldVector(
            msg->twist.twist.angular
        );

    _world_odom_pub.publish(output);
}


void SharedFrameAdapter::cloudCallback(
    const sensor_msgs::PointCloud2::ConstPtr& msg)
{
    sensor_msgs::PointCloud2 output = *msg;

    output.header.frame_id =
        _world_frame;

    try {
        sensor_msgs::PointCloud2Iterator<float>
            iter_x(output, "x");

        sensor_msgs::PointCloud2Iterator<float>
            iter_y(output, "y");

        sensor_msgs::PointCloud2Iterator<float>
            iter_z(output, "z");

        for (;
             iter_x != iter_x.end();
             ++iter_x, ++iter_y, ++iter_z) {

            geometry_msgs::Point local_point;

            local_point.x = *iter_x;
            local_point.y = *iter_y;
            local_point.z = *iter_z;

            const geometry_msgs::Point world_point =
                _transform.localToWorld(
                    local_point
                );

            *iter_x =
                static_cast<float>(
                    world_point.x
                );

            *iter_y =
                static_cast<float>(
                    world_point.y
                );

            *iter_z =
                static_cast<float>(
                    world_point.z
                );
        }
    }
    catch (const std::runtime_error& error) {

        ROS_ERROR_THROTTLE(
            1.0,
            "SharedFrameAdapter cloud transform failed: %s",
            error.what()
        );

        return;
    }

    _world_cloud_pub.publish(output);
}


void SharedFrameAdapter::goalCallback(
    const geometry_msgs::PoseStamped::ConstPtr& msg)
{
    geometry_msgs::PoseStamped output = *msg;

    output.header.stamp =
        ros::Time::now();

    output.header.frame_id =
        _world_frame;

    output.pose.position =
        _transform.localToWorld(
            msg->pose.position
        );

    output.pose.orientation =
        _transform.localToWorldOrientation(
            msg->pose.orientation
        );

    ROS_INFO(
        "Planner goal local -> world: "
        "(%.2f, %.2f, %.2f) -> "
        "(%.2f, %.2f, %.2f)",
        msg->pose.position.x,
        msg->pose.position.y,
        msg->pose.position.z,
        output.pose.position.x,
        output.pose.position.y,
        output.pose.position.z
    );

    _world_goal_pub.publish(output);
}