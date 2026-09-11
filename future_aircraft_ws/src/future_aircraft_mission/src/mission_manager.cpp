#include "future_aircraft_mission/mission_manager.hpp"

MissionManager::MissionManager(
    ros::NodeHandle& nh,
    ros::NodeHandle& pnh)
      : _uav1(nh, pnh, "uav1"),
        _uav2(nh, pnh, "uav2"),
        _mission_state(MissionState::WAIT_READY),
        _state_enter_time(ros::Time::now()),
        _last_offboard_request_time(0),
        _last_arm_request_time(0),
        _last_land_request_time(0),
        _last_disarm_request_time(0),
        _goal_reached_since(0),
        _takeoff_altitude(1.0),
        _takeoff_yaw(0.0),
        _offboard_warmup_s(2.0),
        _service_retry_s(1.0),
        _takeoff_tolerance_m(0.15),
        _landing_altitude_threshold_m(0.20),
        _planner_command_timeout_s(0.5),
        _ego_goal_sent(false),
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
            if (_uav1.startTakeoff(_takeoff_altitude, _takeoff_yaw)) {
                transitionTo(MissionState::TAKEOFF);
            }
        }
        break;
    }

    case MissionState::TAKEOFF:
    {
        if (!_uav1.isOffboard()) {
            break;
        }
        const ros::Time now = ros::Time::now();

        // Phase 3: request and confirm arming.
        if (!_uav1.isArmed()) {

            const bool never_requested = 
                _last_arm_request_time.isZero();

            const bool retry_due = 
                !never_requested && 
                (now - _last_arm_request_time).toSec()
                    >= _service_retry_s;

            if (never_requested || retry_due) {

                _last_arm_request_time = now;

                if (!_uav1.arm()) {
                    ROS_WARN("Arming request failed");
                }
            }
            break;
        }

        // Phase 4: wait until the vehicle climbs to takeoff altitude.
        if (_uav1.hasReachedTakeoffAltitude(
            _takeoff_altitude,
            _takeoff_tolerance_m)) {

                if (_smoke_test) {
                    transitionTo(MissionState::AUTO_LAND);
                }
                else {
                    transitionTo(MissionState::SEND_EGO_GOAL);
                }                
            }

        break;
    }
    
    case MissionState::SEND_EGO_GOAL:
    {
        // EGO has taken over:
        // stop the direct MAVROS source before leaving this state.
        if (_ego_goal_sent &&
            _uav1.hasPlannerCommand() &&
            _uav1.isPlannerCommandFresh(_planner_command_timeout_s)) {
                transitionTo(MissionState::WAIT_REACHED);
                break;
            }

        // EGO has not taken over yet.
        _uav1.publishTakeoffSetpoint(
            _takeoff_altitude,
            _takeoff_yaw
        );

        if (!_ego_goal_sent) {

            geometry_msgs::PoseStamped goal;

            goal.header.stamp = ros::Time::now();
            goal.header.frame_id = "map";

            goal.pose.position.x = _goal_x;
            goal.pose.position.y = _goal_y;
            goal.pose.position.z = _goal_z;
            goal.pose.orientation.w = 1.0;

            _uav1.gotoGoal(goal);
            _ego_goal_sent = true;

            ROS_INFO("EGO goal published");
        }

        const ros::Duration elapsed =
        ros::Time::now() - _state_enter_time;

        if (_ego_goal_sent && elapsed.toSec() >= _ego_handoff_timeout_s) {

            ROS_WARN("EGO handoff timeout");

            transitionTo(MissionState::AUTO_LAND);
            break;
        }

        break;
    }

    case MissionState::WAIT_REACHED:
    {   
        const ros::Time now = ros::Time::now();

        // Planner should still be actively controlling the UAV.
        if (!_uav1.isPlannerCommandFresh(_planner_command_timeout_s)) {

            ROS_WARN("Planner command lost during navigation");

            transitionTo(MissionState::AUTO_LAND);
            break;
        }

        // Outside goal tolerance: settle timer must restart.
        if (!_uav1.hasReachedGoal(_goal_tolerance_m)) {
            _goal_reached_since = ros::Time(0);
            break;
        }

        // First tick inside goal tolerance.
        if (_goal_reached_since.isZero()) {

            _goal_reached_since = now;
            break;
        }

        // Remain inside the tolerance continuously.
        const ros::Duration settled = 
            now - _goal_reached_since;

        if (settled.toSec() >= _goal_settle_s) {
            transitionTo(MissionState::AUTO_LAND);
        }

        break;
    }

    case MissionState::AUTO_LAND:
    {
        const ros::Time now = ros::Time::now();

        if (!_uav1.isAutoLand()) {

            // Keep OFFBOARD alive until AUTO.LAND is confirmed.
            if (_smoke_test || !_uav1.isPlannerCommandFresh(_planner_command_timeout_s)) {
                _uav1.publishCurrentPositionHold(
                    _takeoff_yaw
                );
            }

            const bool never_requested = 
                _last_land_request_time.isZero();
            
            const bool retry_due = 
                !never_requested && 
                (now - _last_land_request_time).toSec()
                    >= _service_retry_s;

            if (never_requested || retry_due) {

                _last_land_request_time = now;

                if (!_uav1.land()) {
                    ROS_WARN("AUTO.LAND request failed");
                }
            }

            break;

        }

        if (_uav1.isNearGround(_landing_altitude_threshold_m)) {
            transitionTo(MissionState::DISARM);
        }

        break;
    }  

    case MissionState::DISARM:
    {
        if (!_uav1.isArmed()) {
            transitionTo(MissionState::FINISHED);
            break;
        }
        
        const ros::Time now = ros::Time::now();

        const bool never_requested = 
            _last_disarm_request_time.isZero();

        const bool retry_due = 
            !never_requested &&
            (now - _last_disarm_request_time).toSec()
                >= _service_retry_s;
        
        if (never_requested || retry_due) {

            _last_disarm_request_time = now;

            if (!_uav1.disarm()) {
                ROS_WARN("Disarm request failed");
            }
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