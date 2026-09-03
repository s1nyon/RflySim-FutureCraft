#pragma once
#include <ros/ros.h>
#include <string>
#include <mavros_msgs/State.h>

class VehicleInterface
{
public:
    VehicleInterface(ros::NodeHandle& nh, ros::NodeHandle& pnh);

    bool isConnected() const;
    bool isArmed() const;
    std::string mode() const;
    bool hasState() const;

private:
    void stateCallback(const mavros_msgs::State::ConstPtr& msg);


    ros::Subscriber _state_sub;

    mavros_msgs::State _state;

    std::string _state_topic;

    bool _has_state;
};