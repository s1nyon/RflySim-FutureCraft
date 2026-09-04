#include "future_aircraft_mission/vehicle_interface.hpp"

VehicleInterface::VehicleInterface(
    ros::NodeHandle& nh,
    ros::NodeHandle& pnh)
    : _has_state(false),
      _has_odom(false),
      _allow_arming_service(false) // Software arming is allowed only in simulation.
{
    pnh.param<std::string>(
        "state_topic",
        _state_topic,
        "mavros/state"
    );
    pnh.param<std::string>(
        "odom_topic",
        _odom_topic,
        "mavros/local_position/odom"
    );
    pnh.param<std::string>(
        "set_mode_service",
        _set_mode_service,
        "mavros/set_mode"
    );
    pnh.param<bool>(
        "allow_arming_service",
        _allow_arming_service,
        false
    );
    pnh.param<std::string>(
        "arming_service",
        _arming_service,
        "mavros/cmd/arming"
    );
    pnh.param<std::string>(
        "position_setpoint_topic",
        _position_setpoint_topic,
        "mavros/setpoint_raw/local"
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
    _position_setpoint_pub = 
        nh.advertise<mavros_msgs::PositionTarget>(
            _position_setpoint_topic,
            10
        );

    _set_mode_client = 
        nh.serviceClient<mavros_msgs::SetMode>(
            _set_mode_service
        );
    _arming_client = 
        nh.serviceClient<mavros_msgs::CommandBool>(
            _arming_service
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

bool VehicleInterface::setArmed(bool armed)
{
    if (!_allow_arming_service) {
        ROS_WARN("Arming service is disabled");
        return false;
    }

    mavros_msgs::CommandBool srv;
    srv.request.value = armed;

    if (!_arming_client.call(srv)) {
        return false;
    }

    return srv.response.success;
}

bool VehicleInterface::arm()
{
    return setArmed(true);
}

bool VehicleInterface::disarm()
{
    return setArmed(false);
}

void VehicleInterface::publishPositionSetpoint(
    const geometry_msgs::Point& position,
    double yaw)
{
    mavros_msgs::PositionTarget target;

    target.header.stamp = ros::Time::now();

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

    target.position = position;
    target.yaw = yaw;

    _position_setpoint_pub.publish(target);
}