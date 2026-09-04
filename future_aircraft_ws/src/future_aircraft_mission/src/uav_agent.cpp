#include "future_aircraft_mission/uav_agent.hpp"

UavAgent::UavAgent(ros::NodeHandle& nh, ros::NodeHandle& pnh, const std::string& uav_name)
    : _uav_name(uav_name), 
      _nh(nh, uav_name), 
      _pnh(pnh, uav_name),
      _vehicle(_nh, _pnh), 
      _ego(_nh, _pnh)
{
    
}

bool UavAgent::isReady() const
{
    return _vehicle.hasState()    && 
           _vehicle.hasOdom()     &&
           _vehicle.isConnected() &&
           !_vehicle.isArmed()    &&
           _vehicle.mode() != "OFFBOARD" &&
           _ego.isPlannerConnected();
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