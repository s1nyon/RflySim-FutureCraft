#include "future_aircraft_mission/uav_agent.hpp"

UavAgent::UavAgent(ros::NodeHandle& nh, ros::NodeHandle& pnh, const std::string& uav_name)
    : _uav_name(uav_name), 
      _nh(nh, uav_name), 
      _pnh(pnh, uav_name),
      _vehicle(_nh, _pnh), 
      _ego(_nh, _pnh),
      _state(State::IDLE)
{
    
}

bool UavAgent::isVehicleReady() const
{
    return _vehicle.hasState() &&
           _vehicle.hasOdom()  &&
           _vehicle.isConnected() &&
           !_vehicle.isArmed() &&
           _vehicle.mode() != "OFFBOARD";
}

bool UavAgent::isReady() const
{
    return isVehicleReady() && _ego.isPlannerConnected();
}

void UavAgent::gotoGoal(
    const geometry_msgs::PoseStamped& goal)
{
    _ego.sendGoal(goal);
}

bool UavAgent::hasReachedGoal(double tolerance_m) const
{
    if (!_vehicle.hasOdom()) {
        return false;
    }

    return _ego.goalReached(_vehicle.position(), tolerance_m);
}

bool UavAgent::requestOffboard()
{
    return _vehicle.setOffboard();
}

bool UavAgent::arm()
{
    return _vehicle.arm();
}

bool UavAgent::land()
{
    return _vehicle.land();
}

bool UavAgent::disarm()
{
    return _vehicle.disarm();
}

bool UavAgent::isArmed() const
{
    return _vehicle.isArmed();
}

bool UavAgent::isOffboard() const
{
    return _vehicle.mode() == "OFFBOARD";
}

bool UavAgent::isAutoLand() const
{
    return _vehicle.mode() == "AUTO.LAND";
}

void UavAgent::publishTakeoffSetpoint(
    double altitude_m,
    double yaw) 
{
    geometry_msgs::Point target;

    target.x = 0.0;
    target.y = 0.0;
    target.z = altitude_m;

    _vehicle.publishPositionSetpoint(target, yaw);
}

bool UavAgent::hasReachedTakeoffAltitude(
    double altitude_m,
    double tolerance_m) const
{
    if (!_vehicle.hasOdom()) {
        return false;
    }

    return _vehicle.position().z >=
        altitude_m - tolerance_m;
}

bool UavAgent::isNearGround(
    double threshold_m) const
{
    if (!_vehicle.hasOdom()) {
        return false;
    }

    return _vehicle.position().z <= threshold_m;
}

bool UavAgent::hasPlannerCommand() const
{
    return _ego.hasPlannerCommand();
}

bool UavAgent::isPlannerCommandFresh(
    double timeout_s) const
{
    return _ego.isPlannerCommandFresh(timeout_s);
}

void UavAgent::publishCurrentPositionHold(double yaw)
{
    if (!_vehicle.hasOdom()) {
        return;
    }

    _vehicle.publishPositionSetpoint(
        _vehicle.position(),
        yaw
    );
}

UavAgent::State UavAgent::state() const
{
    return _state;
}

bool UavAgent::startTakeoff(double altitude_m, double yaw) 
{
    if (_state != State::IDLE) {
        return false;
    }

    _takeoff_altitude = altitude_m;
    _takeoff_yaw = yaw;

    transitionTo(State::TAKING_OFF);

    return true;
}

void UavAgent::transitionTo(State next_state)
{
    _state = next_state;
}