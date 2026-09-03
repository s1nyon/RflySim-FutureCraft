#pragma once
#include <ros/ros.h>
#include <string>
#include <mavros_msgs/State.h>
#include <nav_msgs/Odometry.h>
#include <geometry_msgs/Point.h>

class VehicleInterface
{
public:
    VehicleInterface(ros::NodeHandle& nh, ros::NodeHandle& pnh);

    bool isConnected() const;
    bool isArmed() const;
    std::string mode() const;
    bool hasState() const;

    geometry_msgs::Point position() const;
    bool hasOdom() const;

private:
    void stateCallback(const mavros_msgs::State::ConstPtr& msg);
    void odomCallback(const nav_msgs::Odometry::ConstPtr& msg);

    ros::Subscriber _state_sub;
    ros::Subscriber _odom_sub;

    mavros_msgs::State _state;
    nav_msgs::Odometry _odom;

    std::string _state_topic;
    std::string _odom_topic;

    bool _has_state;
    bool _has_odom;
};