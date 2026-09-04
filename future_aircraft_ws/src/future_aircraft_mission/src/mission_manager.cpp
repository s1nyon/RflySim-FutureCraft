#include "future_aircraft_mission/mission_manager.hpp"

MissionManager::MissionManager(
    ros::NodeHandle& nh,
    ros::NodeHandle& pnh)
    : _uav(nh, pnh, "uav1"),
      _state(State::WAIT_READY),
      _state_enter_time(ros::Time::now()),
      _takeoff_altitude(1.0),
      _takeoff_yaw(0.0)
{

}

void MissionManager::tick()
{
    switch (_state)
    {
    case State::WAIT_READY:
        if (_uav.isReady()) {
            transitionTo(State::TAKEOFF);
        }
        break;
    
    case State::TAKEOFF:
        break;
    
    case State::SEND_EGO_GOAL:
        break;

    case State::WAIT_REACHED:
        break;

    case State::AUTO_LAND:
        break;

    case State::DISARM:
        break;

    case State::FINISHED:
        break;
        
    }
}

void MissionManager::transitionTo(State next_state)
{
    _state = next_state;
    _state_enter_time = ros::Time::now();
}

MissionManager::State MissionManager::state() const
{
    return _state;
}