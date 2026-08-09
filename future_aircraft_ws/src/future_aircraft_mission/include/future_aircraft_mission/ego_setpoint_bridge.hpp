#pragma once 

#include <ros/ros.h>
#include <quadrotor_msgs/PositionCommand.h>
#include <mavros_msgs/PositionTarget.h>
#include <string>

class EgoSetpointBridge
{
public:
    EgoSetpointBridge(ros::NodeHandle& nh, ros::NodeHandle& pnh);

private:

    // EGO command callback
    void plannerCallback(const quadrotor_msgs::PositionCommand::ConstPtr& msg);

    // Publush MAVROS setpoint with fixed frequency
    void publishTimerCallback(const ros::TimerEvent& event);

    // PublishCommand -> PositionTarget
    mavros_msgs::PositionTarget convertCommand(const quadrotor_msgs::PositionCommand& command);

private:
    ros::NodeHandle _nh;
    ros::NodeHandle _pnh;

    ros::Subscriber _planner_sub;
    ros::Publisher _setpoint_pub;
    ros::Timer _publish_timer;

    mavros_msgs::PositionTarget _latest_target;

    std::string _planner_topic;
    std::string _setpoint_topic;

    double _rate_hz;

    double _initial_x;
    double _initial_y;
    double _initial_z;
    double _initial_yaw;    
};
