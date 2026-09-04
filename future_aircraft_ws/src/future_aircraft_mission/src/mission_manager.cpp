#include "future_aircraft_mission/mission_manager.hpp"

MissionManager::MissionManager(
    ros::NodeHandle& nh,
    ros::NodeHandle& pnh)
      : _uav(nh, pnh, "uav1"),
        _state(State::WAIT_READY),
        _state_enter_time(ros::Time::now()),
        _last_offboard_request_time(0),
        _last_arm_request_time(0),
        _takeoff_altitude(1.0),
        _takeoff_yaw(0.0),
        _offboard_warmup_s(2.0),
        _service_retry_s(1.0),
        _takeoff_tolerance_m(0.15)
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
    {
        // OFFBOARD requires a continuous setpoint stream.
        _uav.publishTakeoffSetpoint(
            _takeoff_altitude,
            _takeoff_yaw
        );

        const ros::Time now = ros::Time::now();

        const ros::Duration elapsed = 
            now - _state_enter_time;

        // Phase 1: warm up the OFFBOARD setpoint stream.
        if (elapsed.toSec() < _offboard_warmup_s) {
            break;
        }

        // Phase 2: request and confirm OFFBOARD.
        if (!_uav.isOffboard()) {

            const bool never_requested = 
                _last_offboard_request_time.isZero();

            const bool retry_due = 
                !never_requested &&
                (now - _last_offboard_request_time).toSec()
                    >= _service_retry_s;
            if (never_requested || retry_due) {

                _last_offboard_request_time = now;

                if (!_uav.requestOffboard()) {
                    ROS_WARN("OFFBOARD request failed");
                }
            }
            break;
        }

        // Phase 3: request and confirm arming.
        if (!_uav.isArmed()) {

            const bool never_requested = 
                _last_arm_request_time.isZero();

            const bool retry_due = 
                !never_requested && 
                (now - _last_arm_request_time).toSec()
                    >= _service_retry_s;

            if (never_requested || retry_due) {

                _last_arm_request_time = now;

                if (!_uav.arm()) {
                    ROS_WARN("Arming request failed");
                }
            }
            break;
        }

        // Phase 4: wait until the vehicle climbs to takeoff altitude.
        if (_uav.hasReachedTakeoffAltitude(
            _takeoff_altitude,
            _takeoff_tolerance_m)) {
                transitionTo(State::SEND_EGO_GOAL);
            }

        break;
    }
    
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
    ROS_INFO("Mission state changed");

    _state = next_state;
    _state_enter_time = ros::Time::now();
}

MissionManager::State MissionManager::state() const
{
    return _state;
}