#pragma once

#include <ros/ros.h>

#include <nav_msgs/Odometry.h>
#include <sensor_msgs/PointCloud2.h>
#include <geometry_msgs/PoseStamped.h>

#include <string>

#include "future_aircraft_mission/planar_frame_transform.hpp"

class SharedFrameAdapter
{
public:
    SharedFrameAdapter(
        ros::NodeHandle& nh,
        ros::NodeHandle& pnh
    );

private:
    void odomCallback(
        const nav_msgs::Odometry::ConstPtr& msg
    );

    void cloudCallback(
        const sensor_msgs::PointCloud2::ConstPtr& msg
    );

    void goalCallback(
        const geometry_msgs::PoseStamped::ConstPtr& msg
    );

private:
    ros::NodeHandle _nh;
    ros::NodeHandle _pnh;

    ros::Subscriber _local_odom_sub;
    ros::Subscriber _local_cloud_sub;
    ros::Subscriber _local_goal_sub;

    ros::Publisher _world_odom_pub;
    ros::Publisher _world_cloud_pub;
    ros::Publisher _world_goal_pub;

    std::string _local_odom_topic;
    std::string _local_cloud_topic;
    std::string _local_goal_topic;

    std::string _world_odom_topic;
    std::string _world_cloud_topic;
    std::string _world_goal_topic;

    std::string _world_frame;

    PlanarFrameTransform _transform;
};