#pragma once
#include <ros/ros.h>
#include <string>
#include <mavros_msgs/State.h>
#include <nav_msgs/Odometry.h>
#include <geometry_msgs/Point.h>
#include <mavros_msgs/SetMode.h>
#include <mavros_msgs/CommandBool.h>

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

    bool setOffboard();
    bool land();
    bool arm();
    bool disarm();

private:
    void stateCallback(const mavros_msgs::State::ConstPtr& msg);
    void odomCallback(const nav_msgs::Odometry::ConstPtr& msg);

    bool setMode(const std::string& mode);
    bool setArmed(bool armed);

    ros::Subscriber _state_sub;
    ros::Subscriber _odom_sub;
    ros::ServiceClient _set_mode_client;
    ros::ServiceClient _arming_client;

    mavros_msgs::State _state;
    nav_msgs::Odometry _odom;

    std::string _state_topic;
    std::string _odom_topic;
    std::string _set_mode_service;
    std::string _arming_service;

    bool _has_state;
    bool _has_odom;
    bool _allow_arming_service;
};