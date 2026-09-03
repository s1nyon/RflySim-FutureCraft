#include "future_aircraft_mission/vehicle_interface.hpp"

VehicleInterface::VehicleInterface(
    ros::NodeHandle& nh,
    ros::NodeHandle& pnh)
    : _has_state(false),
      _has_odom(false)
{
    pnh.param<std::string>(
        "state_topic",
        _state_topic,
        "/uav1/mavros/state"
    );
    pnh.param<std::string>(
        "odom_topic",
        _odom_topic,
        "/uav1/mavros/local_position/odom"
    );

    _state_sub = nh.subscribe(
        _state_topic,
        10,
        &VehicleInterface::stateCallback,
        this
    );
    _odom_sub = nh.subscribe(
        _odom_topic,
        10,
        &VehicleInterface::odomCallback,
        this
    );
}

void VehicleInterface::stateCallback(
    const mavros_msgs::State::ConstPtr& msg)
{
    _state = *msg;
    _has_state = true;
}

bool VehicleInterface::isConnected() const 
{
    return _state.connected;
}

bool VehicleInterface::isArmed() const 
{
    return _state.armed;
}

std::string VehicleInterface::mode() const
{
    return _state.mode;
}

bool VehicleInterface::hasState() const
{
    return _has_state;
}

void VehicleInterface::odomCallback(
    const nav_msgs::Odometry::ConstPtr& msg)
{
    _odom = *msg;
    _has_odom = true;
}