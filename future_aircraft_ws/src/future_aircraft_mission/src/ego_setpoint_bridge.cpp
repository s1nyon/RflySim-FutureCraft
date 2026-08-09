#include "future_aircraft_mission/ego_setpoint_bridge.hpp"

EgoSetpointBridge::EgoSetpointBridge(
    ros::NodeHandle& nh,
    ros::NodeHandle& pnh)
    : _nh(nh),
    _pnh(pnh)
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
    _pnh.param<double>(
        "rate_hz",
        _rate_hz,
        20.0
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

    // Create timer
    _publish_timer = _nh.createTimer(
        ros::Duration(1.0 / _rate_hz),
        &EgoSetpointBridge::publishTimerCallback,
        this
    );


    // Create initial target

    
}

void EgoSetpointBridge::plannerCallback(
    const quadrotor_msgs::PositionCommand::ConstPtr& msg)
{
    ROS_INFO("Received planner command");

    _latest_target = convertCommand(*msg);
}

mavros_msgs::PositionTarget 
EgoSetpointBridge::convertCommand(const quadrotor_msgs::PositionCommand& command) {
    mavros_msgs::PositionTarget target;

    target.coordinate_frame = 
        mavros_msgs::PositionTarget::FRAME_LOCAL_NED;

    // TODO: type mask

    target.position.x = command.position.x;
    target.position.y = command.position.y;
    target.position.z = command.position.z;

    target.yaw = command.yaw;

    return target;
}

void EgoSetpointBridge::publishTimerCallback(
    const ros::TimerEvent& event)
{
    _latest_target.header.stamp = ros::Time::now();

    _setpoint_pub.publish(_latest_target);
}
