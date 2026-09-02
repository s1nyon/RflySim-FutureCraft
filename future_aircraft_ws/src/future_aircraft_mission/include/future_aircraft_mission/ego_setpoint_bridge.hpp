#pragma once 

#include <ros/ros.h>
#include <quadrotor_msgs/PositionCommand.h>
#include <mavros_msgs/PositionTarget.h>
#include <geometry_msgs/PoseStamped.h>
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
                                               
    // bridge -> goal
    void goalCallback(const geometry_msgs::PoseStamped::ConstPtr& stamp);
private:
    ros::NodeHandle _nh;
    ros::NodeHandle _pnh;

    ros::Subscriber _planner_sub;
    ros::Subscriber _goal_sub;
    ros::Publisher _setpoint_pub;
    ros::Timer _publish_timer;

    mavros_msgs::PositionTarget _latest_target;

    std::string _planner_topic;
    std::string _setpoint_topic;
    std::string _goal_topic;

    double _rate_hz; 

    bool _has_planner_command;
};
