#include "future_aircraft_mission/ego_setpoint_bridge.hpp"

EgoSetpointBridge::EgoSetpointBridge(
    ros::NodeHandle& nh, // 这里传引用&是不重新造一份nh,直接操作这个已有对象的引用
    ros::NodeHandle& pnh)
    : _nh(nh),
    _pnh(pnh),
    _has_planner_command(false)
{
    // Get parameter
    _pnh.param<std::string>(
        "planner_topic",
        _planner_topic,
        "/uav1/planning/pos_cmd"
    );
    _pnh.param<std::string>(
        "setpoint_topic",
        _setpoint_topic,
        "/uav1/mavros/setpoint_raw/local"
    );
    _pnh.param<std::string>(
        "goal_topic",
        _goal_topic,
        "/uav1/planning/goal"
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

    // Create publisher
    _setpoint_pub = _nh.advertise<mavros_msgs::PositionTarget>(
        _setpoint_topic,
        10
    );

    // Create subscriber
    _planner_sub = _nh.subscribe(
        _planner_topic,
        10,
        &EgoSetpointBridge::plannerCallback,
        this
    );

    _goal_sub = _nh.subscribe(
        _goal_topic,
        10,
        &EgoSetpointBridge::goalCallback,
        this
    );

    // Create timer
    _publish_timer = _nh.createTimer(
        ros::Duration(1.0 / _rate_hz),
        &EgoSetpointBridge::publishTimerCallback,
        this
    );    
}

void EgoSetpointBridge::plannerCallback(
    const quadrotor_msgs::PositionCommand::ConstPtr& msg)
{
    ROS_INFO_ONCE("Received planner command");

    _latest_target = convertCommand(*msg);

    _last_planner_command_time = ros::Time::now();

    _has_planner_command = true;
}

void EgoSetpointBridge::goalCallback(
    const geometry_msgs::PoseStamped::ConstPtr& msg)
{
    ROS_INFO(
        "Received new planner goal: frame=%s, position=(%.2f, %.2f, %.2f)",
        msg->header.frame_id.c_str(),
        msg->pose.position.x,
        msg->pose.position.y,
        msg->pose.position.z
    );

    _has_planner_command = false;
}

mavros_msgs::PositionTarget 
EgoSetpointBridge::convertCommand(const quadrotor_msgs::PositionCommand& command) {
    mavros_msgs::PositionTarget target;

    target.coordinate_frame = 
        mavros_msgs::PositionTarget::FRAME_LOCAL_NED;

    // type mask
    target.type_mask = 
        mavros_msgs::PositionTarget::IGNORE_VX |
        mavros_msgs::PositionTarget::IGNORE_VY |
        mavros_msgs::PositionTarget::IGNORE_VZ |
        mavros_msgs::PositionTarget::IGNORE_AFX |
        mavros_msgs::PositionTarget::IGNORE_AFY |
        mavros_msgs::PositionTarget::IGNORE_AFZ |
        mavros_msgs::PositionTarget::FORCE |
        mavros_msgs::PositionTarget::IGNORE_YAW_RATE;
    
    target.position.x = command.position.x;
    target.position.y = command.position.y;
    target.position.z = command.position.z;

    target.yaw = command.yaw;

    return target;
}

void EgoSetpointBridge::publishTimerCallback(
    const ros::TimerEvent& event)
{
    if (!_has_planner_command) {
        return;
    }

    ros::Duration age = ros::Time::now() - _last_planner_command_time;
    if (age.toSec() > _command_timeout) {

        ROS_WARN(
            "Planner command timeout: age=%.3f s, timeout=%.3f s",
            age.toSec(),
            _command_timeout
        );

        _has_planner_command = false;
        return;
    }

    _latest_target.header.stamp = ros::Time::now();
    _setpoint_pub.publish(_latest_target);
}

