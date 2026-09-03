#pragma once

#include <ros/ros.h>
#include <geometry_msgs/PoseStamped.h>
#include <quadrotor_msgs/PositionCommand.h>
#include <string>

class EgoInterface
{
public:
    EgoInterface(ros::NodeHandle& nh, ros::NodeHandle& pnh);

    void sendGoal(const geometry_msgs::PoseStamped& goal);

    bool hasGoal() const;
    bool hasPlannerCommand() const;

private:
    void plannerCommandCallback(
        const quadrotor_msgs::PositionCommand::ConstPtr& msg
    );

    ros::Publisher  _goal_pub;
    ros::Subscriber _planner_command_sub;

    std::string _goal_topic;
    std::string _planner_command_topic;

    geometry_msgs::PoseStamped _last_goal;

    bool _has_goal;
    bool _has_planner_command;
};