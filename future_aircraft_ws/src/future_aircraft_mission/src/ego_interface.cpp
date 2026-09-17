#include "future_aircraft_mission/ego_interface.hpp"

#include <cmath>


EgoInterface::EgoInterface(
    ros::NodeHandle& nh,
    ros::NodeHandle& pnh)
    : _has_goal(false),
      _has_planner_command(false),
      _handoff_pending(false),
      _last_seen_trajectory_id(-1),
      _goal_baseline_trajectory_id(-1),
      _active_trajectory_id(-1),
      _has_seen_trajectory_id(false)
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


    _goal_pub =
        nh.advertise<geometry_msgs::PoseStamped>(
            _goal_topic,
            10,
            true
        );


    _planner_command_sub =
        nh.subscribe(
            _planner_command_topic,
            10,
            &EgoInterface::plannerCommandCallback,
            this
        );
}


void EgoInterface::publishGoal(
    const geometry_msgs::PoseStamped& goal,
    bool preserve_existing_command)
{
    _last_goal = goal;

    _has_goal = true;


    if (_has_seen_trajectory_id) {

        _goal_baseline_trajectory_id =
            _last_seen_trajectory_id;
    }
    else {

        _goal_baseline_trajectory_id = -1;
    }


    _handoff_pending = true;


    /*
     * Initial navigation:
     * wait until the new trajectory really appears.
     *
     * Retarget:
     * keep the old trajectory alive while EGO replans.
     */
    if (!preserve_existing_command) {

        _has_planner_command = false;

        _active_trajectory_id = -1;
    }


    _goal_pub.publish(goal);
}


void EgoInterface::sendGoal(
    const geometry_msgs::PoseStamped& goal)
{
    publishGoal(
        goal,
        false
    );
}


void EgoInterface::retargetGoal(
    const geometry_msgs::PoseStamped& goal)
{
    publishGoal(
        goal,
        true
    );
}


void EgoInterface::plannerCommandCallback(
    const quadrotor_msgs::PositionCommand::ConstPtr& msg)
{
    const int trajectory_id =
        msg->trajectory_id;

    const ros::Time now =
        ros::Time::now();


    _last_seen_trajectory_id =
        trajectory_id;

    _has_seen_trajectory_id =
        true;


    if (!_has_goal) {
        return;
    }


    /*
     * Waiting for a trajectory generated AFTER the newest goal.
     *
     * During retarget, commands belonging to the currently active
     * trajectory are still considered healthy so the vehicle keeps
     * moving while EGO computes the replacement trajectory.
     */
    if (_handoff_pending) {

        const bool still_old_generation =
            _goal_baseline_trajectory_id >= 0 &&
            trajectory_id <=
                _goal_baseline_trajectory_id;


        if (still_old_generation) {

            if (_has_planner_command &&
                trajectory_id ==
                    _active_trajectory_id) {

                _last_planner_command_time =
                    now;
            }

            return;
        }


        _active_trajectory_id =
            trajectory_id;

        _has_planner_command =
            true;

        _handoff_pending =
            false;

        _last_planner_command_time =
            now;

        ROS_INFO(
            "EGO trajectory handoff accepted: trajectory_id=%d",
            trajectory_id
        );

        return;
    }


    /*
     * Ignore a delayed message belonging to an older trajectory.
     */
    if (_active_trajectory_id >= 0 &&
        trajectory_id <
            _active_trajectory_id) {

        return;
    }


    _active_trajectory_id =
        trajectory_id;

    _has_planner_command =
        true;

    _last_planner_command_time =
        now;
}


bool EgoInterface::hasGoal() const
{
    return _has_goal;
}


bool EgoInterface::hasPlannerCommand() const
{
    return _has_planner_command;
}


bool EgoInterface::isGoalHandoffPending() const
{
    return _handoff_pending;
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
        current_position.x -
        goal_position.x;

    const double dy =
        current_position.y -
        goal_position.y;

    const double dz =
        current_position.z -
        goal_position.z;


    const double distance =
        std::sqrt(
            dx * dx +
            dy * dy +
            dz * dz
        );


    return distance <= tolerance_m;
}


bool EgoInterface::isPlannerCommandFresh(
    double timeout_s) const
{
    if (!hasPlannerCommand()) {
        return false;
    }


    const ros::Duration age =
        ros::Time::now() -
        _last_planner_command_time;


    return age.toSec() <= timeout_s;
}


bool EgoInterface::isPlannerConnected() const
{
    return
        _goal_pub.getNumSubscribers() > 0 &&
        _planner_command_sub.getNumPublishers() > 0;
}