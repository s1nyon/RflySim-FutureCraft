#include "future_aircraft_mission/mission_manager.hpp"

MissionManager::MissionManager(
    ros::NodeHandle& nh,
    ros::NodeHandle& pnh)
      : _uav1(nh, pnh, "uav1"),
        _uav2(nh, pnh, "uav2"),
        _mission_state(MissionState::WAIT_READY),
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

    pnh.param<double>("uav1_goal_x", _uav1_goal_x, 1.0);
    pnh.param<double>("uav1_goal_y", _uav1_goal_y, 0.0);
    pnh.param<double>("uav1_goal_z", _uav1_goal_z, 1.0);

    pnh.param<double>("uav2_goal_x", _uav2_goal_x, 1.0);
    pnh.param<double>("uav2_goal_y", _uav2_goal_y, 0.0);
    pnh.param<double>("uav2_goal_z", _uav2_goal_z, 1.0);
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
            ? (_uav1.isVehicleReady() &&
            _uav2.isVehicleReady())
            : (_uav1.isReady() &&
            _uav2.isReady());

        const bool both_idle =
            _uav1.state() == UavAgent::State::IDLE &&
            _uav2.state() == UavAgent::State::IDLE;

        if (ready && both_idle) {
            const bool uav1_started = _uav1.startTakeoff(_takeoff_altitude, _takeoff_yaw, _takeoff_tolerance_m);
            const bool uav2_started = _uav2.startTakeoff(_takeoff_altitude, _takeoff_yaw, _takeoff_tolerance_m);

            if (uav1_started && uav2_started) {
                transitionTo(MissionState::TAKEOFF);
            }
        }
        break;
    }

    case MissionState::TAKEOFF:
    {
        const bool both_holding =
            _uav1.state() == UavAgent::State::HOLDING &&
            _uav2.state() == UavAgent::State::HOLDING;

        if (!both_holding) {
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

        geometry_msgs::PoseStamped goal1;
        geometry_msgs::PoseStamped goal2;

        goal1.header.stamp = ros::Time::now();
        goal1.header.frame_id = "map";
        goal2.header.stamp = ros::Time::now();
        goal2.header.frame_id = "map";

        goal1.pose.position.x = _uav1_goal_x;
        goal1.pose.position.y = _uav1_goal_y;
        goal1.pose.position.z = _uav1_goal_z;
        goal1.pose.orientation.w = 1.0;

        goal2.pose.position.x = _uav2_goal_x;
        goal2.pose.position.y = _uav2_goal_y;
        goal2.pose.position.z = _uav2_goal_z;
        goal2.pose.orientation.w = 1.0;

        const bool uav1_started =
            _uav1.startNavigation(goal1, _planner_command_timeout_s, _ego_handoff_timeout_s, _goal_tolerance_m, _goal_settle_s);

        const bool uav2_started =
            _uav2.startNavigation(goal2, _planner_command_timeout_s, _ego_handoff_timeout_s, _goal_tolerance_m, _goal_settle_s);

        if (uav1_started && uav2_started) {
            transitionTo(MissionState::WAIT_REACHED);
        }

        break;
    }

    case MissionState::WAIT_REACHED:
    {   
        const bool uav1_done =
            _uav1.state() == UavAgent::State::HOLDING ||
            _uav1.state() == UavAgent::State::ERROR;
        
        const bool uav2_done = 
            _uav2.state() == UavAgent::State::HOLDING ||
            _uav2.state() == UavAgent::State::ERROR;
            
        if (uav1_done && uav2_done) {
            transitionTo(MissionState::AUTO_LAND);
        }

        break;
    }

    case MissionState::AUTO_LAND:
    {
        const auto state1 = _uav1.state();
        const auto state2 = _uav2.state();

        if (state1 == UavAgent::State::HOLDING ||
            state1 == UavAgent::State::ERROR) {
            _uav1.startLanding(_landing_altitude_threshold_m, _service_retry_s, _takeoff_yaw);
        }

        if (state2 == UavAgent::State::HOLDING ||
            state2 == UavAgent::State::ERROR) {
            _uav2.startLanding(_landing_altitude_threshold_m, _service_retry_s, _takeoff_yaw);
        }

        if (_uav1.state() == UavAgent::State::FINISHED &&
            _uav2.state() == UavAgent::State::FINISHED) {
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
}

MissionManager::MissionState MissionManager::state() const
{
    return _mission_state;
}