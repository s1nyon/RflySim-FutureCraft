#include "future_aircraft_mission/vehicle_interface.hpp"

VehicleInterface::VehicleInterface(
    ros::NodeHandle& nh,
    ros::NodeHandle& pnh)
    : _has_state(false)
{
    pnh.param<std::string>(
        "state_topic",
        _state_topic,
        "/uav1/mavros/state"
    );

    _state_sub = nh.subscribe(
        _state_topic,
        10,
        &VehicleInterface::stateCallback,
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