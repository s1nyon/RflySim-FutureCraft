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

bool UavAgent::startTakeoff(double altitude_m, double yaw, double tolerance_m) 
{
    if (_state != State::IDLE) {
        return false;
    }

    _takeoff_altitude = altitude_m;
    _takeoff_yaw = yaw;
    _takeoff_tolerance_m = tolerance_m;

    transitionTo(State::TAKING_OFF);

    _takeoff_start_time = ros::Time::now();
    _last_offboard_request_time = ros::Time(0);
    _last_arm_request_time = ros::Time(0);

    return true;
}

bool UavAgent::startNavigation(
    const geometry_msgs::PoseStamped& goal,
    double planner_command_timeout_s,
    double handoff_timeout_s,
    double goal_tolerance_m,
    double goal_settle_s)    
{
    if (_state != State::HOLDING) {
        return false;
    }

    if (!_vehicle.hasOdom()) {
        return false;
    }

    _navigation_hold_position = _vehicle.position();
    _planner_command_timeout_s = planner_command_timeout_s;
    _planner_handoff_timeout_s = handoff_timeout_s;
    _goal_tolerance_m = goal_tolerance_m;
    _goal_settle_s = goal_settle_s;

    _navigation_start_time = ros::Time::now();
    _goal_reached_since = ros::Time(0);

    gotoGoal(goal);
    transitionTo(State::WAITING_FOR_PLANNER);

    return true;
}


void UavAgent::transitionTo(State next_state)
{
    _state = next_state;
}

void UavAgent::tick()
{
    switch (_state)
    {
    case State::IDLE:
    {
        break;
    }

    case State::TAKING_OFF:
    {
        publishTakeoffSetpoint(_takeoff_altitude, _takeoff_yaw);

        const ros::Time now = ros::Time::now();
        const ros::Duration elapsed = now - _takeoff_start_time;

        if (elapsed.toSec() < 2.0) {
            break;
        }

        if (!isOffboard()) {

            const bool never_requested = 
                _last_offboard_request_time.isZero();

            const bool retry_due = 
                !never_requested &&
                (now - _last_offboard_request_time).toSec()
                    >= 1.0;
            if (never_requested || retry_due) {

                _last_offboard_request_time = now;

                if (!requestOffboard()) {
                    ROS_WARN("%s OFFBOARD request failed",
                    _uav_name.c_str());
                }
            }
            break;
        }

        if (!isArmed()) {

            const bool never_requested = 
                _last_arm_request_time.isZero();

            const bool retry_due = 
                !never_requested &&
                (now - _last_arm_request_time).toSec() >= 1.0;

            if (never_requested || retry_due) {

                _last_arm_request_time = now;

                if (!arm()) {
                    ROS_WARN("%s arming request failed", _uav_name.c_str());
                }
            }
            break;
        }

        if (hasFinishedTakeoff()) {
            
            _navigation_hold_position = _vehicle.position();
            transitionTo(State::HOLDING);
        }

        break;
    }

    case State::HOLDING:
    {
        if (isOffboard()) {
            _vehicle.publishPositionSetpoint(
                _navigation_hold_position,
                _takeoff_yaw
            );
        }
        
        break;
    }

    case State::WAITING_FOR_PLANNER:
    {
        if (hasPlannerCommand() &&
            isPlannerCommandFresh(_planner_command_timeout_s)) {
                transitionTo(State::NAVIGATING);
                break;
        }

        const ros::Duration elapsed = 
            ros::Time::now() - _navigation_start_time;
        
        if (elapsed.toSec() >= _planner_handoff_timeout_s) {

            ROS_WARN("%s EGO handoff timeout", _uav_name.c_str());
            transitionTo(State::ERROR);
            break;
        }

        if (isOffboard()) {
            _vehicle.publishPositionSetpoint(
                _navigation_hold_position,
                _takeoff_yaw
            );
        }
        break;
    }

    case State::NAVIGATING:
    {
        const ros::Time now = ros::Time::now();

        if (!isPlannerCommandFresh(_planner_command_timeout_s)) {
            ROS_WARN("%s planner command lost", _uav_name.c_str());

            transitionTo(State::ERROR);

            break;
        }

        if (!hasReachedGoal(_goal_tolerance_m)) {
            _goal_reached_since = ros::Time(0);
            break;
        }

        if (_goal_reached_since.isZero()) {
            _goal_reached_since = now;
            break;
        }

        const ros::Duration settled = 
            now - _goal_reached_since;

        if (settled.toSec() >= _goal_settle_s) {
            _navigation_hold_position = _vehicle.position();

            transitionTo(State::HOLDING);
        }
        break;
    }

    case State::LANDING:
    {
        break;
    }

    case State::FINISHED:
    {
        break;
    }

    case State::ERROR:
    {
        break;
    }
}

bool UavAgent::hasFinishedTakeoff() const
{
    return isArmed() &&
           hasReachedTakeoffAltitude(
               _takeoff_altitude,
               _takeoff_tolerance_m
           );
}