#include "future_aircraft_mission/mission_manager.hpp"

MissionManager::MissionManager(
    ros::NodeHandle& nh,
    ros::NodeHandle& pnh)
      : _uav1(nh, pnh, "uav1"),
        _uav2(nh, pnh, "uav2"),
        _mission_state(MissionState::WAIT_READY),
        _state_enter_time(ros::Time::now()),
        _takeoff_altitude(1.0),
        _takeoff_yaw(0.0),
        _service_retry_s(1.0),
        _takeoff_tolerance_m(0.15),
        _landing_altitude_threshold_m(0.20),
        _planner_command_timeout_s(0.5),
        _smoke_test(false),
        _goal_tolerance_m(0.30),
        _goal_settle_s(1.0),
        _ego_handoff_timeout_s(5.0)
{
    pnh.param<bool>(
        "smoke_test",
        _smoke_test,
        false
    );

    pnh.param<double>("goal_x", _goal_x, 1.0);
    pnh.param<double>("goal_y", _goal_y, 0.0);
    pnh.param<double>("goal_z", _goal_z, 1.0);
}

void MissionManager::tick()
{
    _uav1.tick();
    _uav2.tick();

    switch (_mission_state)
    {
    case MissionState::WAIT_READY:
    {
        const bool ready = 
            _smoke_test
            ? _uav1.isVehicleReady()
            : _uav1.isReady();

        if (ready) {
            if (_uav1.startTakeoff(_takeoff_altitude, _takeoff_yaw, _takeoff_tolerance_m)) {
                transitionTo(MissionState::TAKEOFF);
            }
        }
        break;
    }

    case MissionState::TAKEOFF:
    {
        if (_uav1.state() != UavAgent::State::HOLDING) {
            break;
        }

        if (_smoke_test) {
            transitionTo(MissionState::AUTO_LAND);
        } else {
            transitionTo(MissionState::SEND_EGO_GOAL);
        }
        break;
    }
    
    case MissionState::SEND_EGO_GOAL:
    {

        geometry_msgs::PoseStamped goal;

        goal.header.stamp = ros::Time::now();
        goal.header.frame_id = "map";

        goal.pose.position.x = _goal_x;
        goal.pose.position.y = _goal_y;
        goal.pose.position.z = _goal_z;
        goal.pose.orientation.w = 1.0;

        if (_uav1.startNavigation(
                goal,
                _planner_command_timeout_s,
                _ego_handoff_timeout_s,
                _goal_tolerance_m,
                _goal_settle_s)) {
            
            transitionTo(MissionState::WAIT_REACHED);
        }

        break;
    }

    case MissionState::WAIT_REACHED:
    {   
        if (_uav1.state() == UavAgent::State::HOLDING) {
            transitionTo(MissionState::AUTO_LAND);
            break;
        }

        if (_uav1.state() == UavAgent::State::ERROR) {
            ROS_WARN("UAV1 navigation failed");
            transitionTo(MissionState::AUTO_LAND);
            break;
        }

        break;
    }

    case MissionState::AUTO_LAND:
    {
        const auto state = _uav1.state();

        if (state == UavAgent::State::HOLDING ||
            state == UavAgent::State::ERROR) {

            _uav1.startLanding(
                _landing_altitude_threshold_m,
                _service_retry_s,
                _takeoff_yaw
            );

            break;
        }

        if (state == UavAgent::State::FINISHED) {
            transitionTo(MissionState::FINISHED);
        }

        break;
    }


    case MissionState::FINISHED:
        break;
        
    }
}

void MissionManager::transitionTo(MissionState next_state)
{
    ROS_INFO("Mission state changed");

    _mission_state = next_state;
    _state_enter_time = ros::Time::now();
}

MissionManager::MissionState MissionManager::state() const
{
    return _mission_state;
}