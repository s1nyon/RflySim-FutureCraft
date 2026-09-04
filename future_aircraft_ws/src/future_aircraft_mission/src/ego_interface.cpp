#include "future_aircraft_mission/ego_interface.hpp"
#include <cmath>

EgoInterface::EgoInterface(
    ros::NodeHandle& nh,
    ros::NodeHandle& pnh)
    : _has_goal(false),
      _has_planner_command(false)
{
    pnh.param<std::string>(
        "goal_topic",
        _goal_topic,
        "planning/goal"
    );
    pnh.param<std::string>(
        "planner_command_topic",
        _planner_command_topic,
        "planning/pos_cmd"
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
}

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
    (void)msg;

    _has_planner_command = true;
    _last_planner_command_time = ros::Time::now();
}

bool EgoInterface::hasGoal() const 
{
    return _has_goal;
}

bool EgoInterface::hasPlannerCommand() const 
{
    return _has_planner_command;
}

bool EgoInterface::goalReached(
    const geometry_msgs::Point& current_position,
    double tolerance_m) const
{
    if (!_has_goal) {
        return false;
    }

    const geometry_msgs::Point& goal_position = 
        _last_goal.pose.position;

    const double dx = 
        current_position.x - goal_position.x;
    const double dy = 
        current_position.y - goal_position.y;
    const double dz = 
        current_position.z - goal_position.z;

    const double distance = 
        std::sqrt(dx * dx + dy * dy + dz * dz);

    return distance <= tolerance_m;
}

bool EgoInterface::isPlannerCommandFresh(
    double timeout_s) const
{
    if (!hasPlannerCommand()) {
        return false;
    }

    const ros::Duration age = 
    ros::Time::now() - _last_planner_command_time;

    return age.toSec() <= timeout_s;
}

bool EgoInterface::isPlannerConnected() const
{
    return _goal_pub.getNumSubscribers() > 0 &&
           _planner_command_sub.getNumPublishers() > 0;
}