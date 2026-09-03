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
    pnh.param<std::string>(
        "set_mode_service",
        _set_mode_service,
        "/uav1/mavros/set_mode"
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

    _set_mode_client = 
        nh.serviceClient<mavros_msgs::SetMode>(
            _set_mode_service
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

bool VehicleInterface::hasOdom() const
{
    return _has_odom;
}

geometry_msgs::Point VehicleInterface::position() const
{
    return _odom.pose.pose.position;
}

bool VehicleInterface::setMode(const std::string& mode)
{
    mavros_msgs::SetMode srv;

    srv.request.custom_mode = mode;

    if (!_set_mode_client.call(srv)) {
        return false;
    }

    return srv.response.mode_sent;
}

bool VehicleInterface::setOffboard()
{
    return setMode("OFFBOARD");
}

bool VehicleInterface::land()
{
    return setMode("AUTO.LAND");
}
