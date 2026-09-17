#include "future_aircraft_mission/ego_setpoint_bridge.hpp"
#include <cmath>

namespace
{

constexpr double kPi =
    3.14159265358979323846;

double degreesToRadians(double degrees)
{
    return degrees * kPi / 180.0;
}

}  // namespace


EgoSetpointBridge::EgoSetpointBridge(
    ros::NodeHandle& nh,
    ros::NodeHandle& pnh)
    : _nh(nh),
      _pnh(pnh),
      _has_planner_command(false),
      _has_received_goal(false),
      _last_seen_trajectory_id(-1),
      _goal_baseline_trajectory_id(-1),
      _has_seen_trajectory_id(false),
      _use_shared_frame(false),
      _handoff_pending(false),
      _active_trajectory_id(-1)
{
    _pnh.param<std::string>(
        "planner_topic",
        _planner_topic,
        "planning/pos_cmd"
    );

    _pnh.param<std::string>(
        "setpoint_topic",
        _setpoint_topic,
        "mavros/setpoint_raw/local"
    );

    _pnh.param<std::string>(
        "goal_topic",
        _goal_topic,
        "planning/goal"
    );

    _pnh.param<double>(
        "rate_hz",
        _rate_hz,
        20.0
    );

    _pnh.param<double>(
        "command_timeout",
        _command_timeout,
        0.5
    );

    _pnh.param<bool>(
        "shared_frame/enabled",
        _use_shared_frame,
        false
    );

    double origin_x = 0.0;
    double origin_y = 0.0;
    double origin_z = 0.0;
    double origin_yaw_deg = 0.0;

    _pnh.param<double>(
        "shared_frame/origin_x",
        origin_x,
        0.0
    );

    _pnh.param<double>(
        "shared_frame/origin_y",
        origin_y,
        0.0
    );

    _pnh.param<double>(
        "shared_frame/origin_z",
        origin_z,
        0.0
    );

    _pnh.param<double>(
        "shared_frame/origin_yaw_deg",
        origin_yaw_deg,
        0.0
    );

    _frame_transform =
        PlanarFrameTransform(
            _use_shared_frame,
            origin_x,
            origin_y,
            origin_z,
            degreesToRadians(origin_yaw_deg)
        );

    _setpoint_pub =
        _nh.advertise<mavros_msgs::PositionTarget>(
            _setpoint_topic,
            10
        );

    _planner_sub =
        _nh.subscribe(
            _planner_topic,
            10,
            &EgoSetpointBridge::plannerCallback,
            this
        );

    _goal_sub =
        _nh.subscribe(
            _goal_topic,
            10,
            &EgoSetpointBridge::goalCallback,
            this
        );

    _publish_timer =
        _nh.createTimer(
            ros::Duration(
                1.0 / _rate_hz
            ),
            &EgoSetpointBridge::publishTimerCallback,
            this
        );

    if (_use_shared_frame) {
        ROS_INFO(
            "EgoSetpointBridge shared-frame conversion enabled: "
            "origin=(%.3f, %.3f, %.3f), yaw=%.2f deg",
            origin_x,
            origin_y,
            origin_z,
            origin_yaw_deg
        );
    }
}


void EgoSetpointBridge::plannerCallback(
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


    if (!_has_received_goal) {
        return;
    }


    if (_handoff_pending) {

        const bool still_old_generation =
            _goal_baseline_trajectory_id >= 0 &&
            trajectory_id <=
                _goal_baseline_trajectory_id;


        if (still_old_generation) {

            /*
             * Retarget case:
             * keep following the trajectory that was already active.
             */
            if (_has_planner_command &&
                trajectory_id ==
                    _active_trajectory_id) {

                _latest_target =
                    convertCommand(*msg);

                _last_planner_command_time =
                    now;
            }

            return;
        }


        /*
         * First command belonging to the newly generated trajectory.
         */
        _active_trajectory_id =
            trajectory_id;

        _handoff_pending =
            false;
    }
    else {

        if (_active_trajectory_id >= 0 &&
            trajectory_id <
                _active_trajectory_id) {

            return;
        }


        _active_trajectory_id =
            trajectory_id;
    }


    _latest_target =
        convertCommand(*msg);


    _last_planner_command_time =
        now;


    _has_planner_command =
        true;


    ROS_INFO_ONCE(
        "Received planner command"
    );
}


void EgoSetpointBridge::goalCallback(
    const geometry_msgs::PoseStamped::ConstPtr& msg)
{
    ROS_INFO(
        "Received new planner goal: "
        "frame=%s, position=(%.2f, %.2f, %.2f)",
        msg->header.frame_id.c_str(),
        msg->pose.position.x,
        msg->pose.position.y,
        msg->pose.position.z
    );


    if (_has_seen_trajectory_id) {

        _goal_baseline_trajectory_id =
            _last_seen_trajectory_id;
    }
    else {

        _goal_baseline_trajectory_id =
            -1;
    }


    _has_received_goal =
        true;


    _handoff_pending =
        true;


    /*
     * IMPORTANT:
     *
     * Do NOT clear _has_planner_command here.
     *
     * If an old trajectory is already active, let it continue
     * controlling the UAV until a newer trajectory_id appears.
     *
     * For the very first goal _has_planner_command is already false,
     * so startup behaviour remains generation-safe.
     */
}


mavros_msgs::PositionTarget
EgoSetpointBridge::convertCommand(
    const quadrotor_msgs::PositionCommand& command)
{
    mavros_msgs::PositionTarget target;

    target.coordinate_frame =
        mavros_msgs::PositionTarget::FRAME_LOCAL_NED;

    target.type_mask =
        mavros_msgs::PositionTarget::IGNORE_VX |
        mavros_msgs::PositionTarget::IGNORE_VY |
        mavros_msgs::PositionTarget::IGNORE_VZ |
        mavros_msgs::PositionTarget::IGNORE_AFX |
        mavros_msgs::PositionTarget::IGNORE_AFY |
        mavros_msgs::PositionTarget::IGNORE_AFZ |
        mavros_msgs::PositionTarget::FORCE |
        mavros_msgs::PositionTarget::IGNORE_YAW_RATE;

    const geometry_msgs::Point local_position =
        _frame_transform.worldToLocal(
            command.position
        );

    target.position =
        local_position;

    target.yaw =
        _frame_transform.worldToLocalYaw(
            command.yaw
        );

    return target;
}


void EgoSetpointBridge::publishTimerCallback(
    const ros::TimerEvent& event)
{
    if (!_has_planner_command) {
        return;
    }

    const ros::Duration age =
        ros::Time::now() -
        _last_planner_command_time;

    if (age.toSec() >
        _command_timeout) {

        ROS_WARN(
            "Planner command timeout: "
            "age=%.3f s, timeout=%.3f s",
            age.toSec(),
            _command_timeout
        );

        _has_planner_command =
            false;

        return;
    }

    _latest_target.header.stamp =
        ros::Time::now();

    _setpoint_pub.publish(
        _latest_target
    );
}