#include "future_aircraft_mission/ego_interface.hpp"

EgoInterface::EgoInterface(
    ros::NodeHandle& nh,
    ros::NodeHandle& pnh)
    : _has_goal(false),
      _has_planner_command(false)
{
    pnh.param<std::string>(
        "goal_topic",
        _goal_topic,
        "/uav1/planning/goal"
    );
    pnh.param<std::string>(
        "planner_command_topic",
        _planner_command_topic,
        "/uav1/planning/pos_cmd"
    );

    _goal_pub = nh.advertise<geometry_msgs::PoseStamped>(
        _goal_topic,
        10,
        true // This is a latched publisher.
    );
    _planner_command_sub = nh.subscribe(
        _planner_command_topic,
        10,
        &EgoInterface::plannerCommandCallback,
        this
    );
};

void EgoInterface::sendGoal(
    const geometry_msgs::PoseStamped& goal)
{
    _last_goal = goal;
    _has_goal = true;

    _has_planner_command = false;

    _goal_pub.publish(goal);
}

void EgoInterface::plannerCommandCallback(
    const quadrotor_msgs::PositionCommand::ConstPtr& msg)
{
    _has_planner_command = true;
}

bool EgoInterface::hasGoal() const 
{
    return _has_goal;
}

bool EgoInterface::hasPlannerCommand() const 
{
    return _has_planner_command;
}